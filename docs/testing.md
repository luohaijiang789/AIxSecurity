# Testing and acceptance

`make test`: deterministic tests, no network or model credentials.
`make demo`: two files, one static candidate, no source execution.
`python -m pip install .`: packaging smoke check.

Exit codes: 0 report complete; 2 invalid target/output or I/O error; 3 partial analysis.

CI config and Docker recipe are provided. Local unit results do not imply remote CI or Docker build passed. Candidate count is not vulnerability recall/precision.
