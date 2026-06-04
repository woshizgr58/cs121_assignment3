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

11. `master of software engineering` - Common terms and noisy course/data files could outrank the MSWE page.
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

- Full query token use: query terms are stemmed and retained, including common words and numeric tokens, to match the no-stopping requirement.
- TF-IDF ranked retrieval: documents containing any query term are considered. Their TF-IDF contributions are accumulated and ranked, allowing relevant partial matches instead of requiring Boolean AND matches.
- URL-aware ranking: documents whose URL contains query terms receive a general bonus. This helps official pages such as faculty profiles, program pages, lab pages, and event pages surface when their URL clearly matches the query.
- Raw-file and dataset penalties: `.txt`, `.bib`, `.csv`, `.log`, and dataset-path URLs receive a mild penalty so large text dumps do not dominate normal web-search queries.
- URL deduplication: near-duplicate URLs such as `/`, `/index`, and `/index.html` are collapsed in final results.
- Runtime control: expensive URL reranking is applied only to a preliminary top window, preserving better rankings while keeping query response time practical.

## Final Performance

The final searcher was tested on all 20 queries after loading the seek table and document map:

- Average query response time: `118.4 ms`
- Maximum query response time: `230.2 ms`
- Queries completed under the `300 ms` developer-track target: `20/20`

## How To Run Tests

Build a fresh disk index folder containing `index.txt`, `index_seek.json`, and `doc_map.json`, then run:

```bash
python3 searcher.py --index-dir output --query "master of software engineering" --top 5
python3 searcher.py --index-dir output
```
