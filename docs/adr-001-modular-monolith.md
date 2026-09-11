# ADR 001: Modular monolith

Status: accepted for the initial scaffold.

A single installable Python package keeps analysis and evidence contracts testable. Model providers and program analyzers depend on explicit ports. No empty frontend, message queue or microservice cluster is introduced. A durable ledger and sandbox require separate acceptance tests before claiming production readiness.
