"""Trusted AST subprocess entry point; never imports the audited project."""
import json
import sys
from pathlib import Path

# Direct script execution with -I: import only this installed/source package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from aixsecurity.adapters.python_ast import PythonAstAnalyzer


def main():
    request = json.load(sys.stdin)
    try:
        findings = PythonAstAnalyzer().analyze(request['path'], request['source'], request['digest'])
        result = {'findings': [finding.to_dict() for finding in findings]}
    except (SyntaxError, UnicodeError, RecursionError) as exc:
        result = {'error': type(exc).__name__}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    main()
