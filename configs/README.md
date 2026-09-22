# Runtime configuration
Use `audit --config configs/default.json`. Missing fields take dataclass defaults;
unknown/duplicate keys and invalid values are rejected. AI must remain false until
a provider is implemented. Positive integer limits reject booleans.
`max_files` counts encountered files, including unsupported suffixes.
`max_total_bytes` counts actual reads, including parse failures; a single lookahead
byte may exceed the budget to detect truncation. Excluded subtrees are not counted.

`worker_timeout_seconds` is a positive integer (default 10). The CLI passes it to
the per-file subprocess analyzer. Direct library callers choose their analyzer.
