# Architecture

## Decision: modular monolith first

CLI → Application audit service → Analyzer port → Python AST adapter → Finding → JSON evidence report.

- `domain/`: typed candidate/evidence objects; no model or filesystem dependency.
- `application/`: traversal, bounds, coverage accounting and atomic report output.
- `adapters/`: deterministic analyzers; CodeQL and model clients are future adapters.
- `ports.py`: analyzer and hypothesis provider interfaces.
- `tests/`: unit and integration contracts, including failure paths.
- `examples/`: synthetic demo inputs; never imported by the audit engine.

## Invariants

Candidates are not confirmed vulnerabilities. Each analyzed file has a SHA-256. Skipped/failed inputs are visible as partial coverage. Output is outside source tree. Source files are never executed. Symbolic links are excluded, but hostile concurrent path replacement is not hardened: immutable input snapshots are required.

## Roadmap (not implemented)

1. CodeQL DB adapter and path evidence import; pin database/query versions.
2. Model-backed hypothesis provider with explicit opt-in, redaction and token budgets.
3. Reviewer workflow, finding deduplication and independently sourced verdicts.
4. SQLite run ledger, resumable steps and content-addressed artifact store.
5. Isolated dynamic verification with approval boundary and independent truth sets.

Do not split these into network services until workload/isolation measurements justify it.
