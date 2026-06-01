# Milestone 3 Test Queries

This document lists the 20 queries used to evaluate the search engine for ranking effectiveness and response time. The labels describe the behavior before the Milestone 3 searcher changes.

## Queries That Initially Performed Well

1. `cristina lopes` - Returned relevant Cristina Lopes pages, although the faculty profile was not always ranked first.
2. `machine learning` - Returned plausible ML research/course pages quickly.
3. `ACM` - Returned ACM-related publication and news pages.
4. `student affairs` - Returned undergraduate/student-facing ICS pages.
5. `artificial intelligence` - Returned AI course pages and related content.
6. `data mining` - Returned plausible ML/data mining pages.
7. `donald bren school` - Returned ICS school news and official pages.
8. `secure systems` - Returned security lab/publication pages.
9. `software engineering masters` - Returned software engineering pages, though noisy pages sometimes ranked too high.
10. `informatics graduate program` - Returned informatics/graduate-related pages.

## Queries That Initially Performed Poorly

11. `master of software engineering` - Stopword `of` over-constrained the query, and noisy course/data files could outrank the MSWE page.
12. `database systems` - Large dataset text files sometimes outranked database group/course pages.
13. `computer vision` - Generic homework/text pages could outrank actual computer vision pages.
14. `mondego lab` - Results were indirect news/profile pages rather than lab/project pages.
15. `undergraduate admissions` - Some unrelated project/course pages ranked above admissions or undergraduate pages.
16. `ics faculty` - Course pages with repeated ICS/faculty terms outranked faculty-directory-style pages.
17. `course catalogue` - Unrelated pages using the word catalogue could rank above course-related pages.
18. `networked systems` - Dataset/publication dumps could outrank networked systems pages.
19. `game design` - Raw dataset pages could outrank actual game design pages.
20. `uci calendar` - Dataset pages could outrank calendar pages.

## General Changes Made

- Query stopword filtering: common query words such as `of`, `the`, and `and` are ignored when there are other content words. The index still keeps stopwords; this only prevents query-time over-constraining.
- Soft fallback for longer queries: strict AND is still used when enough results exist, but longer natural-language queries can fall back to majority-term matching when strict AND is too brittle.
- URL-aware ranking: documents whose URL contains query terms receive a general bonus. This helps official pages such as faculty profiles, program pages, lab pages, and event pages surface when their URL clearly matches the query.
- Raw-file and dataset penalties: `.txt`, `.bib`, `.csv`, `.log`, and dataset-path URLs receive a mild penalty so large text dumps do not dominate normal web-search queries.
- URL deduplication: near-duplicate URLs such as `/`, `/index`, and `/index.html` are collapsed in final results.
- Runtime control: expensive URL reranking is applied only to a preliminary top window, preserving better rankings while keeping query response time practical.

## How To Run Tests

Build or use an existing disk index folder containing `index.txt`, `index_seek.json`, and `doc_map.json`, then run:

```bash
python3 searcher.py --index-dir output --query "master of software engineering" --top 5
python3 searcher.py --index-dir output
```

The interactive command is useful for the TA demo because the index seek table and doc map load once, then each query runs without restarting the program.
