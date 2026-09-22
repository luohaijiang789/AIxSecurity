# Findings
The initial directory contained only README placeholders. A complete project foundation is not the same as complete AI audit capability. Start with deterministic evidence contracts and explicitly leave model/CodeQL providers unimplemented.

Iteration 1: the old config was unused and empty inputs incorrectly completed.
These are addressed without adding runtime dependencies. Run tracking is separate
from resumability; filesystem snapshotting and CPU isolation remain future work.

AXS-003: versions were duplicated in CLI/package metadata without a release
ledger. CLI now imports package version and CI checks metadata/changelog agreement.
A SQLite failure while handling Ctrl-C could override exit 130; regression added.
