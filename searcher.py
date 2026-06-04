import argparse
import heapq
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse
 
try:
    from nltk.stem import PorterStemmer
except ImportError:
    print("Missing nltk. Run: pip install nltk", file=sys.stderr)
    raise SystemExit(1)
 
TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
IMPORTANT_BOOST = 5
URL_MATCH_BOOST = 4.0
EXACT_URL_PHRASE_BOOST = 8.0
RAW_FILE_PENALTY = 0.55
DATASET_PATH_PENALTY = 0.75
stemmer = PorterStemmer()
 

 
def tokenize_query(query: str) -> list[str]:
    raw_tokens = [tok.lower() for tok in TOKEN_RE.findall(query)]
    stemmed = [stemmer.stem(tok) for tok in raw_tokens]
    return list(dict.fromkeys(stemmed))


def tokenize_url(url: str) -> set[str]:
    parsed = urlparse(url)
    text = unquote(f"{parsed.netloc} {parsed.path} {parsed.query}")
    return set(tokenize_query(text.replace("_", " ").replace("-", " ")))


def normalize_url_for_dedup(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    for suffix in ("/index.html", "/index.htm", "/index.php", "/index"):
        if path.lower().endswith(suffix):
            path = path[:-len(suffix)]
            break
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}?{parsed.query}".rstrip("?")


def url_quality_multiplier(url: str) -> float:
    lower = url.lower()
    multiplier = 1.0
    if lower.endswith((".txt", ".bib", ".log", ".csv")):
        multiplier *= RAW_FILE_PENALTY
    if "/datasets/" in lower or "/dataset/" in lower:
        multiplier *= DATASET_PATH_PENALTY
    return multiplier
 
 
def parse_postings(postings_str: str) -> list[tuple[int, int, int]]:
    postings = []
    for chunk in postings_str.split("|"):
        parts = chunk.split(",")
        postings.append((int(parts[0]), int(parts[1]), int(parts[2])))
    return postings
 
 
 
class IndexReader:
    def __init__(self, index_dir: Path):
        seek_path = index_dir / "index_seek.json"
        index_path = index_dir / "index.txt"
        doc_map_path = index_dir / "doc_map.json"
 
        if not seek_path.exists():
            raise FileNotFoundError(f"index_seek.json not found in {index_dir}")
        if not index_path.exists():
            raise FileNotFoundError(f"index.txt not found in {index_dir}")
        if not doc_map_path.exists():
            raise FileNotFoundError(f"doc_map.json not found in {index_dir}")
 
        print("Loading seek table...", end=" ", flush=True)
        with seek_path.open("r", encoding="utf-8") as f:
            self.seek_table: dict[str, int] = json.load(f)
        print("done.")
 
        print("Loading doc map...", end=" ", flush=True)
        with doc_map_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        self.doc_map: dict[int, str] = {int(k): v for k, v in raw.items()}
        self.N = len(self.doc_map)
        print("done.")
 
        self._index_file = index_path.open("rb")   # binary for precise seeking
 
    def get_postings(self, token: str) -> list[tuple[int, int, int]] | None:
        """Seek directly to the token's line and return its postings, or None."""
        offset = self.seek_table.get(token)
        if offset is None:
            return None
        self._index_file.seek(offset)
        line = self._index_file.readline().decode("utf-8").rstrip("\n")
        _, postings_str = line.split("\t", 1)
        return parse_postings(postings_str)
 
    def close(self):
        self._index_file.close()
 
 
 
def search(query: str, reader: IndexReader, top_k: int = 5):
    tokens = tokenize_query(query)
    if not tokens:
        return []

    postings_by_token: list[tuple[str, list[tuple[int, int, int]]]] = []
    for token in tokens:
        postings = reader.get_postings(token)
        if postings is not None:
            postings_by_token.append((token, postings))

    if not postings_by_token:
        return []

    available_tokens = [token for token, _ in postings_by_token]
    scores: dict[int, float] = {}
    matched_terms: dict[int, int] = {}

    for token, postings in postings_by_token:
        df = len(postings)
        idf = math.log((reader.N + 1) / (df + 1)) + 1.0
        for doc_id, tf, imp in postings:
            matched_terms[doc_id] = matched_terms.get(doc_id, 0) + 1
            effective_tf = tf + imp * IMPORTANT_BOOST
            tf_weight = (1 + math.log(effective_tf)) if effective_tf > 0 else 0.0
            scores[doc_id] = scores.get(doc_id, 0.0) + tf_weight * idf

    rerank_limit = max(250, top_k * 50)
    rerank_doc_ids = {
        doc_id for doc_id, _ in heapq.nlargest(
            rerank_limit, scores.items(), key=lambda x: x[1]
        )
    }

    for doc_id in list(scores):
        coverage = matched_terms[doc_id] / len(available_tokens)
        scores[doc_id] *= 0.75 + 0.25 * coverage

        if doc_id not in rerank_doc_ids:
            continue

        url = reader.doc_map[doc_id]
        url_tokens = tokenize_url(url)
        url_matches = sum(1 for token in available_tokens if token in url_tokens)
        if url_matches:
            scores[doc_id] += url_matches * URL_MATCH_BOOST

        normalized_query = " ".join(available_tokens)
        normalized_url = " ".join(sorted(url_tokens))
        if normalized_query and normalized_query in normalized_url:
            scores[doc_id] += EXACT_URL_PHRASE_BOOST

        scores[doc_id] *= url_quality_multiplier(url)

    ranked = heapq.nlargest(max(top_k * 20, 100), scores.items(), key=lambda x: x[1])
    unique_results = []
    seen_urls = set()
    for doc_id, score in ranked:
        url = reader.doc_map[doc_id]
        dedup_key = normalize_url_for_dedup(url)
        if dedup_key in seen_urls:
            continue
        seen_urls.add(dedup_key)
        unique_results.append((score, url))
        if len(unique_results) == top_k:
            break

    return unique_results

 
def run_once(query: str, reader: IndexReader, top_k: int):
    t0 = time.perf_counter()
    results = search(query, reader, top_k)
    elapsed_ms = (time.perf_counter() - t0) * 1000
 
    print(f'\nTop {top_k} results for: "{query}"  ({elapsed_ms:.1f} ms)')
    print("-" * 60)
    if not results:
        print("No results found.")
    else:
        for rank, (score, url) in enumerate(results, 1):
            print(f"{rank}. [{score:.4f}] {url}")
 
 
def run_interactive(reader: IndexReader, top_k: int):
    print("Search engine ready. Type a query and press Enter. Ctrl+C to quit.\n")
    while True:
        try:
            query = input("Query> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye.")
            break
        if not query:
            continue
        run_once(query, reader, top_k)
 
 
def main():
    parser = argparse.ArgumentParser(description="Search the inverted index.")
    parser.add_argument("--index-dir", type=Path, default=Path("."),
                        help="Folder with index.txt, index_seek.json, doc_map.json")
    parser.add_argument("--query", type=str, default=None,
                        help="Run a single query and exit")
    parser.add_argument("--top", type=int, default=5,
                        help="Number of results to return (default: 5)")
    args = parser.parse_args()
 
    reader = IndexReader(args.index_dir)
    try:
        if args.query:
            run_once(args.query, reader, args.top)
        else:
            run_interactive(reader, args.top)
    finally:
        reader.close()
 
 
if __name__ == "__main__":
    main()
    
