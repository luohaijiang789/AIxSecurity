# Contributing

Run `make test` and `make demo` before a pull request. Changes to findings require schema compatibility tests. Target code is data, never imported or executed. Model suggestions must remain unverified candidates. Do not commit customer code, credentials or generated reports.

Use an AXS item from [the roadmap](docs/roadmap.md). Keep each change bounded and add failure-path tests. Run `python3 scripts/check_project.py` in addition to tests. Update CHANGELOG for observable changes and add an ADR for architecture decisions. Use the PR template; record CI separately from local tests. Revert shared commits rather than rewriting history.
