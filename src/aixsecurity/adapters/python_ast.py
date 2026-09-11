"""Small demonstration rule, not taint analysis or vulnerability verification."""
import ast
from ..domain.models import Finding

class PythonAstAnalyzer:
    name = "python-ast-demo-v1"

    def analyze(self, path, source, digest):
        tree = ast.parse(source, filename=path)
        result = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                result.append(Finding("PY-DYNAMIC-EXEC", path, node.lineno,
                    "Dynamic execution call: review input origin, aliasing and scope manually.", digest))
        return sorted(result, key=lambda item: item.line)
