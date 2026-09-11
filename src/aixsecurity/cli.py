import argparse
import json
import sys
from pathlib import Path
from .application.audit import audit
from .adapters.python_ast import PythonAstAnalyzer

def main():
    parser = argparse.ArgumentParser(prog="aixsecurity", description="Evidence-first white-box auditing scaffold")
    parser.add_argument("--version", action="version", version="0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("audit", help="Collect Python AST demonstration candidates")
    scan.add_argument("target", type=Path)
    scan.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit(args.target, PythonAstAnalyzer(), args.output)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "files_analyzed": result["files_analyzed"],
        "candidates": len(result["findings"]), "ai_enabled": result["ai_enabled"]}))
    return 0 if result["status"] == "completed" else 3
