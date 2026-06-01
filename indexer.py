import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urldefrag
 
try:
    from bs4 import BeautifulSoup
    from nltk.stem import PorterStemmer
except ImportError as error:
    print(
        "Missing dependency. Run: pip install beautifulsoup4 nltk",
        file=sys.stderr,
    )
    raise SystemExit(1) from error
 
 
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
IMPORTANT_TAGS = ("title", "h1", "h2", "h3", "b", "strong")
FLUSH_EVERY = 10_000
 
stemmer = PorterStemmer()
 
 
 
def walk_json_files(dataset_path: Path) -> Iterable[Path]:
    for root, _, files in os.walk(dataset_path):
        for filename in files:
            if filename.lower().endswith(".json"):
                yield Path(root) / filename
 
 
def tokenize(text: str) -> list[str]:
    tokens = []
    for tok in TOKEN_RE.findall(text or ""):
        tok = tok.lower()
        if tok.isdigit():
            continue
        tokens.append(stemmer.stem(tok))
    return tokens
 
 
def extract_important_text(soup: BeautifulSoup) -> str:
    chunks = []
    for tag in soup.find_all(IMPORTANT_TAGS):
        chunks.append(tag.get_text(" ", strip=True))
    return " ".join(chunks)
 
 
def process_document(json_path: Path):
    with json_path.open("r", encoding="utf-8", errors="replace") as f:
        page = json.load(f)
 
    url = page.get("url")
    content = page.get("content")
 
    if not isinstance(url, str) or not url.strip():
        raise ValueError("missing or invalid url")
    if not isinstance(content, str):
        content = ""
 
    clean_url, _ = urldefrag(url)
    soup = BeautifulSoup(content, "html.parser")
 
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
 
    important_text = extract_important_text(soup)
    visible_text = soup.get_text(" ", strip=True)
 
    term_counts = Counter(tokenize(visible_text))
    important_term_counts = Counter(tokenize(important_text))
 
    return clean_url, term_counts, important_term_counts
 
 
 
def flush_partial(partial: dict, partial_dir: Path, flush_num: int) -> Path:
    """
    Write one partial index to disk as a sorted text file.
    Format per line:  token\tdoc_id,tf,imp|doc_id,tf,imp|...
    """
    path = partial_dir / f"partial_{flush_num:04d}.txt"
    with path.open("w", encoding="utf-8") as f:
        for token in sorted(partial):
            postings_str = "|".join(
                f"{doc_id},{tf},{imp}"
                for doc_id, tf, imp in sorted(partial[token], key=lambda x: x[0])
            )
            f.write(f"{token}\t{postings_str}\n")
    return path
 

 
def merge_partials(partial_paths: list[Path], output_index: Path, output_seek: Path):
    """
    k-way merge all partial index files into one sorted index.txt.
    Simultaneously builds index_seek.json (token → byte offset).
    """
    import heapq
 
    handles = [p.open("r", encoding="utf-8") for p in partial_paths]
 
    def read_line(fh):
        line = fh.readline()
        if not line:
            return None
        token, postings_str = line.rstrip("\n").split("\t", 1)
        postings = []
        for chunk in postings_str.split("|"):
            parts = chunk.split(",")
            postings.append((int(parts[0]), int(parts[1]), int(parts[2])))
        return token, postings
 
    heap = []
    buffers = {}
    for i, fh in enumerate(handles):
        entry = read_line(fh)
        if entry:
            heapq.heappush(heap, (entry[0], i))
            buffers[i] = entry
 
    seek_table = {}
    byte_offset = 0
 
    with output_index.open("w", encoding="utf-8") as out:
        while heap:
            token, fi = heapq.heappop(heap)
            merged_postings = list(buffers[fi][1])
            entry = read_line(handles[fi])
            if entry:
                heapq.heappush(heap, (entry[0], fi))
                buffers[fi] = entry
 
            while heap and heap[0][0] == token:
                _, fi2 = heapq.heappop(heap)
                merged_postings.extend(buffers[fi2][1])
                entry = read_line(handles[fi2])
                if entry:
                    heapq.heappush(heap, (entry[0], fi2))
                    buffers[fi2] = entry
 
            merged_postings.sort(key=lambda x: x[0])
 
            postings_str = "|".join(f"{d},{t},{imp}" for d, t, imp in merged_postings)
            line = f"{token}\t{postings_str}\n"
 
            seek_table[token] = byte_offset
            out.write(line)
            byte_offset += len(line.encode("utf-8"))
 
    for fh in handles:
        fh.close()
 
    with output_seek.open("w", encoding="utf-8") as f:
        json.dump(seek_table, f, separators=(",", ":"), sort_keys=True)
 
    return seek_table
 

 
def build_index(dataset_path: Path, output_dir: Path):
    partial_dir = output_dir / "partials"
    partial_dir.mkdir(parents=True, exist_ok=True)
 
    doc_map = {}
    indexed_documents = 0
    files_seen = 0
    flush_count = 0
    partial_paths = []
 
    buffer: dict[str, list] = defaultdict(list)
 
    for json_path in walk_json_files(dataset_path):
        files_seen += 1
        try:
            url, term_counts, important_term_counts = process_document(json_path)
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as e:
            print(f"Skipping {json_path}: {e}")
            continue
 
        doc_id = indexed_documents
        indexed_documents += 1
        doc_map[doc_id] = url
 
        for token, tf in term_counts.items():
            buffer[token].append((doc_id, tf, important_term_counts.get(token, 0)))
 
        for token, imp in important_term_counts.items():
            if token not in term_counts:
                buffer[token].append((doc_id, 0, imp))
 
        if indexed_documents % FLUSH_EVERY == 0:
            flush_count += 1
            path = flush_partial(buffer, partial_dir, flush_count)
            partial_paths.append(path)
            buffer.clear()
            print(f"  Flushed partial index #{flush_count} at {indexed_documents} docs "
                  f"({files_seen} files scanned)...")
 
        if indexed_documents % 5000 == 0:
            print(f"  Processed {indexed_documents} documents...")
 
    if buffer:
        flush_count += 1
        path = flush_partial(buffer, partial_dir, flush_count)
        partial_paths.append(path)
        buffer.clear()
        print(f"  Flushed final partial index #{flush_count}.")
 
    print(f"\nMerging {len(partial_paths)} partial indexes...")
    index_path = output_dir / "index.txt"
    seek_path = output_dir / "index_seek.json"
    seek_table = merge_partials(partial_paths, index_path, seek_path)
    print("Merge complete.")
 
    for p in partial_paths:
        p.unlink()
    partial_dir.rmdir()
 
    doc_map_path = output_dir / "doc_map.json"
    with doc_map_path.open("w", encoding="utf-8") as f:
        json.dump(doc_map, f, separators=(",", ":"))
 
    index_size_kb = index_path.stat().st_size / 1024
    analytics = {
        "number_of_indexed_documents": indexed_documents,
        "number_of_unique_tokens": len(seek_table),
        "total_index_size_kb": index_size_kb,
    }
    analytics_path = output_dir / "analytics.json"
    with analytics_path.open("w", encoding="utf-8") as f:
        json.dump(analytics, f, indent=2, sort_keys=True)
 
    print("\nIndexer analytics")
    print("-----------------")
    print(f"Indexed documents : {analytics['number_of_indexed_documents']}")
    print(f"Unique tokens     : {analytics['number_of_unique_tokens']}")
    print(f"Index size on disk: {analytics['total_index_size_kb']:.2f} KB")
    print(f"Partial flushes   : {flush_count}")
 
 
 
def resolve_dataset_path(input_path: Path):
    if not input_path.is_file() or input_path.suffix.lower() != ".zip":
        return None, None
    temp_dir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(input_path, "r") as zf:
        zf.extractall(temp_dir.name)
    extracted = Path(temp_dir.name)
    subdirs = [p for p in extracted.iterdir() if p.is_dir()]
    if len(subdirs) == 1:
        dataset_path = subdirs[0]
    else:
        dataset_path = extracted
    return temp_dir, dataset_path
 
 
def main():
    parser = argparse.ArgumentParser(
        description="Build a disk-based inverted index from crawled ICS JSON files."
    )
    parser.add_argument("dataset", type=Path,
                        help="Path to dataset folder or developer.zip")
    parser.add_argument("-o", "--output-dir", type=Path, default=Path("."),
                        help="Output directory (default: current dir)")
    args = parser.parse_args()
 
    if not args.dataset.exists():
        raise FileNotFoundError(f"Dataset not found: {args.dataset}")
 
    temp_dir, dataset_path = resolve_dataset_path(args.dataset)
    if dataset_path is None:
        dataset_path = args.dataset
 
    if not dataset_path.is_dir():
        raise NotADirectoryError(f"Dataset must be a directory or zip: {args.dataset}")
 
    args.output_dir.mkdir(parents=True, exist_ok=True)
 
    try:
        print(f"Building index from {dataset_path}...")
        build_index(dataset_path, args.output_dir)
    finally:
        if temp_dir:
            temp_dir.cleanup()
 
 
if __name__ == "__main__":
    main()