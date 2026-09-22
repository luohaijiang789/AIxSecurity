# Progress
Implemented CLI, domain objects, analyzer port, AST adapter, bounded traversal, report export, tests, CI recipe and non-root container recipe. No target code is executed or uploaded by the audit command.

Verified 10 offline tests, two-file demonstration (one candidate), wheel installation and original-file rollback hashes. Official PyPI was used after the configured mirror returned no build dependencies. GitHub remote: https://github.com/luohaijiang789/AIxSecurity (private). Docker build is not locally verified.

Iteration 1 (2026-09-22): implemented strict effective config, file/read budgets,
report schema v2, candidate fingerprints, coverage and no-supported-files status,
SQLite run envelopes and list/show commands. Regression suite: 22 local tests.
Changes remain local; no new GitHub push or remote CI run in this iteration.
Recovery/worker isolation/AI integration are not implemented in this tranche.

Project operations (2026-09-22): prepared 0.2.0 with CHANGELOG, AXS roadmap,
Issue/PR templates and CI consistency checks. Local source tests: 25 passed.
Fixed interrupted-ledger-write handling and explicit report UTF-8 encoding.
Packaging first attempted without build isolation; local setuptools was absent.
Retried standard isolated packaging via official PyPI. Remote delivery evidence
is recorded by the associated Git commit and GitHub Actions run, not inferred
from local tests. Prior "no push" statements describe the previous iteration.
Package installation succeeded (0.2.0); installed-package suite: 25 passed.
CLI outside repository reports 0.2.0; demo analyzed 2 files with 1 candidate.

AXS-004 / 0.3.0: implemented application-level source snapshots and schema v3.
33 source tests pass locally. Snapshot artifacts contain local source copies and
are excluded from Git. Filesystem-atomic capture and worker isolation remain open.
Installed 0.3.0 also passed all 33 tests; demo captured/analyzed 2 files and produced
1 candidate with a schema-v3 report and persisted content-addressed snapshot.

AXS-005 / 0.4.0: CLI isolated workers, timeout/reaping, failure continuation,
evidence protocol validation. 41 local source tests passed, including real child
timeout and crash fixtures. No target execution; no OS sandbox/memory limit claim.
Installed 0.4.0 also passed 41 tests. Demo confirmed execution_mode=subprocess,
2 analyzed files and 1 candidate.
