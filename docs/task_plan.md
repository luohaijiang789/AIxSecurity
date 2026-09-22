# Project foundation plan
- [x] Inspect initial skeleton and authenticated GitHub account.
- [x] Implement installable modular monolith and deterministic demonstration pipeline.
- [x] Verify 10 tests, wheel installation and rollback on an independent copy.
- [x] Configure private GitHub repository and main branch publication.

## Iteration 1
- [x] Preserve baseline and run original 10 tests.
- [x] Implement validated configuration and effective runtime limits.
- [x] Add deterministic fingerprints and explicit coverage/no-input status.
- [x] Persist run envelopes and implement runs list/show.
- [x] Finish regression and independent rollback verification (see external verification bundle).
- [ ] Next iteration: immutable snapshots, isolated workers, checkpoints/resume.

## Project operations / AXS-003
- [x] Add versioned changelog, roadmap with stable IDs and acceptance criteria.
- [x] Add Issue/PR templates and offline consistency gate in CI.
- [x] Fix interrupt error handling and explicit UTF-8 report writing.
- [x] Run 25 local regression tests; preserve pre-turn working tree snapshot.
- [x] AXS-004 immutable source snapshots (completed in 0.3.0).

## AXS-004
- [x] Separate capture from analysis; persist content-addressed blobs and manifest.
- [x] Detect observable source changes; preserve parse-failure evidence hashes.
- [x] Add eight snapshot regression tests; 33 total tests pass locally.
- [x] AXS-005 isolated worker (completed in 0.4.0).

## AXS-005
- [x] CLI uses one trusted worker subprocess per file.
- [x] Timeout/crash/protocol failures yield partial and continue.
- [x] 8 worker regression tests; 41 total source tests pass.
- [ ] Next: AXS-006 checkpoint/resume.
