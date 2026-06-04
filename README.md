# CS 121 Search Engine - Milestone 3

This submission contains a disk-based inverted indexer and a console search
component for the full ICS developer corpus.

## Requirements

- Python 3.10 or newer
- Dependencies listed in `requirements.txt`
- `developer.zip` supplied by the course staff

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## Build the Index

Generated indexes are intentionally not included in the submission. Build a
fresh index from the developer corpus:

```bash
python3 indexer.py developer.zip -o output
```

The indexer writes:

- `output/index.txt`: sorted disk-based inverted index
- `output/index_seek.json`: token-to-byte-offset seek table
- `output/doc_map.json`: document-ID-to-URL map
- `output/analytics.json`: index statistics

The indexer flushes a partial index every 5,000 documents and merges all partial
indexes after processing the corpus.

## Run the Searcher

Interactive console:

```bash
python3 searcher.py --index-dir output
```

Single query:

```bash
python3 searcher.py --index-dir output --query "machine learning" --top 5
```

The searcher retrieves the union of documents containing any query term, ranks
them using accumulated TF-IDF scores and important-word boosts, then prints
ranked URLs.

## Submission Files

- `indexer.py`: index construction and partial-index merging
- `searcher.py`: disk-based retrieval and ranked search
- `M3_Report.pdf`: Milestone 3 report
- `M3_Report.tex`: editable report source
- `m3_test_queries.md`: evaluation queries and performance summary
- `requirements.txt`: Python dependencies

## Verified Results

The complete 55,393-document index contains 388,597 unique tokens and is
approximately 91 MB. Across the 20 evaluation queries, the current searcher
averaged 118.4 ms, reached a maximum of 230.2 ms, and completed all 20 queries
under the 300 ms developer-track target.
