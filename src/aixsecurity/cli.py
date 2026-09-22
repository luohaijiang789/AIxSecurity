import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .application.audit import audit
from .adapters.python_ast import PythonAstAnalyzer
from .adapters.ledger import RunLedger
from .config import load_config
from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="aixsecurity", description="Evidence-first white-box auditing scaffold")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("audit", help="Collect Python AST demonstration candidates")
    scan.add_argument("target", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    scan.add_argument("--config", type=Path)
    scan.add_argument("--ledger", type=Path, default=Path("runs/ledger.sqlite3"))
    runs = sub.add_parser("runs", help="Inspect persistent run envelopes")
    runs.add_argument("--ledger", type=Path, default=Path("runs/ledger.sqlite3"))
    actions = runs.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    show = actions.add_parser("show")
    show.add_argument("run_id")
    args = parser.parse_args(argv)
    ledger = None
    run_id = None
    try:
        if args.command == "runs":
            if not args.ledger.is_file():
                raise ValueError("Ledger does not exist")
            ledger = RunLedger(args.ledger)
            result = ledger.list() if args.action == "list" else ledger.show(args.run_id)
            print(json.dumps(result, ensure_ascii=False))
            return 0
        config = load_config(args.config)
        target = args.target.resolve(strict=True)
        output = args.output.resolve()
        ledger_path = args.ledger.resolve()
        if not target.is_dir():
            raise ValueError("Target must be a directory")
        for path in (output, ledger_path):
            if path == target or target in path.parents:
                raise ValueError("Output and ledger must be outside the target directory")
        if output == ledger_path or output in ledger_path.parents or ledger_path in output.parents:
            raise ValueError("Output and ledger paths must be independent")
        if args.config and args.config.resolve() in (output, ledger_path):
            raise ValueError("Output and ledger must not overwrite configuration")
        ledger = RunLedger(ledger_path)
        run_id = ledger.start(target, config.to_dict())
        result = audit(target, PythonAstAnalyzer(), output, config)
        ledger.finish(run_id, report=result)
        print(json.dumps({"run_id": run_id, "status": result["status"],
            "files_analyzed": result["files_analyzed"],
            "candidates": len(result["findings"]), "ai_enabled": result["ai_enabled"]}))
        return 0 if result["status"] == "completed" else 3
    except KeyboardInterrupt:
        if ledger and run_id:
            try:
                ledger.finish(run_id, error="Interrupted by user")
            except sqlite3.Error:
                pass
        return 130
    except (OSError, ValueError, sqlite3.Error, RecursionError) as exc:
        if ledger and run_id:
            try:
                ledger.finish(run_id, error=f"{type(exc).__name__}: {exc}")
            except sqlite3.Error:
                pass
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if ledger:
            ledger.close()
