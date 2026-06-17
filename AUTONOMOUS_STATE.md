# Autonomous Worker — State

Handoff from interactive session 2026-06-17. Do the TOP unchecked task. Update this file every run.

- [x] T1 - Update workshop-playbook.md (tell-ban list, density floor, image+brand discipline, exemplar pointer)
- [x] T2 - workshop.py control-flow rc + retry file-hash/rerun-imagegen + record-only-passed-signatures
- [x] T3 - Hard asset hygiene across ALL pages (block {{ token / placeholder-text imagery / picsum); fail-closed
- [x] T4 - Proportional void RATIO + ink-coverage veto + hero ceiling, all pages/viewports
- [x] T5 - Retrieval MMR/de-dup + corpus-thin nonzero-rc skip + grow thin pools
- [ ] T6 - Diversity discriminators (type-scale within xl; semantic concept bucket)
- [ ] T7 - Kinetic at-rest motion assertion + deterministic void veto wiring + drop "ignore placeholder" prompt line
- [ ] T8 - Casa Umbral regression-fixture test

## Log
(worker appends one line per run: ISO time | task | commit | tests)
2026-06-17 | T1 playbook premium bar (tell-ban + density floor + image/brand discipline + casa-umbral exemplar) added to all 3 awwwards kit_generation prompts | f1fae10 | 59 passed
2026-06-17 | T2 oneshot rc nonzero when flagged (_oneshot_rc; register_weekly keeps trying) + retry-stop via _kit_tree_hash with rerun-imagegen on final retry + record diversity signature only for PASSED kits | 2407dca | 65 passed (added test_kit_tree_hash, test_oneshot_rc; staged as HEAD-isolated patch leaving unrelated pre-existing workshop.py edits uncommitted)
2026-06-17 | T3 static asset-hygiene gate (scripts/asset_hygiene.py): blocks unsubstituted {{TOKEN}}, picsum URLs, and PLACEHOLDER-text imagery (inline SVG + referenced local files) across every *.html page; wired into run_quality_gate fail-CLOSED + recorded in verdict.json; verified it flags the D1 editorial-studio kit (all 3 defect classes) and passes casa-umbral exemplar clean | b3a0d64 | 72 passed (added test_asset_hygiene.py x7; HEAD-isolated patch leaving pre-existing workshop.py WIP uncommitted)
2026-06-17 | T4 proportional void RATIO + screenshot ink-coverage veto + uncapped hero_vh ceiling, worst-case across ALL pages x desktop+mobile. render_metrics: void_ratio (sum-gaps/page_h), _ink_coverage (15-bit-hist bg + L1 ink fraction), hero_vh_ratio (uncapped hero/vh), viewport param + render_metrics_all(). quality_floor_config: hero_vh_max=2.0, void_ratio_max=0.60, ink_coverage_min=0.05 (calibrated vs real kits: void_ratio<=0.464, ink>=0.13, hero_vh<=1.37 -> all clear w/ margin; D1/sparse-flag still gated by single-gap+hygiene). gate wired via render_metrics_all worst-case. Verified casa-umbral exemplar clears all 3 new vetoes | a7a277b | 75 passed (added 3 tests; HEAD-isolated patch leaving pre-existing workshop.py WIP uncommitted)
2026-06-17 | T5 retrieval MMR/de-dup: retrieve_awwwards_refs now reranks a WIDER pool (rerank_n=min(max(k*3,8),len)) then MMR-selects k via mmr_select() — greedily trades reranker relevance (raw 0..1) against max structural Jaccard overlap with prior picks (lambda 0.7), so a thin pool can't return k near-identical refs (same hero_archetype + section_topology + signature concept). structural_tokens() fingerprints diversity-bearing fields only (palette excluded). corpus-thin nonzero-rc skip already wired from T2 (oneshot rc=1 -> register_weekly advances to next pair); "grow thin pools" = wider rerank candidate window | 0eef7a5 | 79 passed (added 4 tests to test_awwwards_retrieval.py; pure-fn unit tests need no sl mocking; HEAD-isolated patch leaving pre-existing WIP uncommitted)
