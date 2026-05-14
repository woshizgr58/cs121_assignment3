import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import urldefrag

try:
    from bs4 import BeautifulSoup
    from nltk.stem import PorterStemmer
except ImportError as error:
    print(
        "Missing dependency. Please install beautifulsoup4 and nltk before running "
        "this indexer: pip install beautifulsoup4 nltk",
        file=sys.stderr,
    )
    raise SystemExit(1) from error


TOKEN_RE = re.compile(r"[A-Za-z0-9]+")
IMPORTANT_TAGS = ("title", "h1", "h2", "h3", "b", "strong")

stemmer = PorterStemmer()


def walk_json_files(dataset_path: Path) -> Iterable[Path]:
    """Yield every JSON file under dataset_path recursively."""
    for root, _, files in os.walk(dataset_path):
        for filename in files:
            if filename.lower().endswith(".json"):
                yield Path(root) / filename


def tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alphanumeric Porter-stemmed tokens."""
    tokens = TOKEN_RE.findall(text or "")
    return [stemmer.stem(token.lower()) for token in tokens]


def extract_important_text(soup: BeautifulSoup) -> str:
    """Extract text from tags that should receive important-term counts."""
    important_chunks = []
    for tag in soup.find_all(IMPORTANT_TAGS):
        important_chunks.append(tag.get_text(" ", strip=True))
    return " ".join(important_chunks)


def process_document(json_path: Path) -> Tuple[str, Counter, Counter]:
    """
    Process one crawled page JSON file.

    Returns:
        (defragmented_url, term_counts, important_term_counts)
    """
    with json_path.open("r", encoding="utf-8", errors="replace") as file:
        page = json.load(file)

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


def save_json(data, output_path: Path) -> None:
    """Save data as readable JSON, creating parent directories if needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, sort_keys=True)


def get_file_size_kb(path: Path) -> float:
    """Return a file size in KB."""
    return path.stat().st_size / 1024


def build_index(
    dataset_path: Path, progress_interval: int = 1000
) -> Tuple[Dict[str, List[dict]], Dict[int, str], int]:
    """
    Build an in-memory inverted index.

    The nested dictionary shape makes it easy to later replace this function
    with partial-index flushing while preserving the final postings format.
    """
    index = defaultdict(dict)
    doc_map = {}
    indexed_documents = 0
    files_seen = 0

    for json_path in walk_json_files(dataset_path):
        files_seen += 1
        try:
            url, term_counts, important_term_counts = process_document(json_path)
        except (json.JSONDecodeError, OSError, UnicodeError, ValueError) as error:
            print(f"Skipping {json_path}: {error}")
            continue

        doc_id = indexed_documents
        indexed_documents += 1
        doc_map[doc_id] = url

        for token, tf in term_counts.items():
            index[token][doc_id] = {
                "doc_id": doc_id,
                "tf": tf,
                "important_tf": important_term_counts.get(token, 0),
            }

        # Keep important-only tokens discoverable even if BeautifulSoup's visible
        # text extraction changes for unusual malformed pages.
        for token, important_tf in important_term_counts.items():
            if token not in term_counts:
                index[token][doc_id] = {
                    "doc_id": doc_id,
                    "tf": 0,
                    "important_tf": important_tf,
                }

        if indexed_documents % progress_interval == 0:
            print(
                f"Indexed {indexed_documents} documents "
                f"({files_seen} JSON files scanned, {len(index)} unique tokens)..."
            )

    serializable_index = {
        token: sorted(postings.values(), key=lambda posting: posting["doc_id"])
        for token, postings in sorted(index.items())
    }

    return serializable_index, doc_map, indexed_documents


def resolve_dataset_path(input_path: Path) -> Optional[tempfile.TemporaryDirectory]:
    """
    If input_path is a zip file, extract it and return the temporary directory.
    For normal directories, return None.
    """
    if not input_path.is_file() or input_path.suffix.lower() != ".zip":
        return None

    temp_dir = tempfile.TemporaryDirectory()
    with zipfile.ZipFile(input_path, "r") as zip_file:
        zip_file.extractall(temp_dir.name)
    return temp_dir


def print_analytics(analytics: dict) -> None:
    """Print milestone analytics in a readable format."""
    print("\nIndexer analytics")
    print("-----------------")
    print(f"Indexed documents: {analytics['number_of_indexed_documents']}")
    print(f"Unique tokens: {analytics['number_of_unique_tokens']}")
    print(f"Index size on disk: {analytics['total_index_size_kb']:.2f} KB")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an inverted index from crawled ICS webpage JSON files."
    )
    parser.add_argument(
        "dataset",
        type=Path,
        help="Path to the extracted dataset folder or dataset zip file.",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory where index.json, doc_map.json, and analytics.json are saved.",
    )
    args = parser.parse_args()

    input_path = args.dataset
    if not input_path.exists():
        raise FileNotFoundError(f"Dataset path does not exist: {input_path}")

    temp_dir = resolve_dataset_path(input_path)
    dataset_path = Path(temp_dir.name) if temp_dir is not None else input_path

    if not dataset_path.is_dir():
        raise NotADirectoryError(f"Dataset must be a directory or zip file: {input_path}")

    try:
        print(f"Building index from {dataset_path}...")
        index, doc_map, indexed_documents = build_index(dataset_path)

        index_path = args.output_dir / "index.json"
        doc_map_path = args.output_dir / "doc_map.json"
        analytics_path = args.output_dir / "analytics.json"

        print("Writing index.json...")
        save_json(index, index_path)
        print("Writing doc_map.json...")
        save_json(doc_map, doc_map_path)

        analytics = {
            "number_of_indexed_documents": indexed_documents,
            "number_of_unique_tokens": len(index),
            "total_index_size_kb": get_file_size_kb(index_path),
        }

        print("Writing analytics.json...")
        save_json(analytics, analytics_path)
        print_analytics(analytics)
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


if __name__ == "__main__":
    main()
