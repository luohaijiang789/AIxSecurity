"""Executable dependency rules for the modular monolith."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'src' / 'aixsecurity'


def imports(path):
    relative = path.relative_to(ROOT).with_suffix('')
    module = 'aixsecurity.' + '.'.join(relative.parts)
    package = module.rsplit('.', 1)[0]
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parts = package.split('.')
                prefix = '.'.join(parts[:len(parts) - node.level + 1])
                name = prefix + ('.' + node.module if node.module else '')
            else:
                name = node.module or ''
            yield name
            yield from (name + '.' + alias.name for alias in node.names)


class ArchitectureTests(unittest.TestCase):
    def test_domain_and_application_do_not_depend_on_infrastructure(self):
        forbidden = ('aixsecurity.adapters', 'aixsecurity.entrypoints',
                     'aixsecurity.composition', 'aixsecurity.cli', 'aixsecurity.doctor',
                     'sqlite3', 'subprocess', 'socket', 'urllib.request', 'http.client')
        for layer in ('domain', 'application'):
            for path in (ROOT / layer).rglob('*.py'):
                for dependency in imports(path):
                    with self.subTest(file=str(path), dependency=dependency):
                        self.assertFalse(any(dependency == f or dependency.startswith(f + '.') for f in forbidden))
                        if layer == 'domain':
                            self.assertFalse(dependency.startswith('aixsecurity.application'))

    def test_entrypoints_use_composition_not_adapters(self):
        for path in (ROOT / 'entrypoints').rglob('*.py'):
            for dependency in imports(path):
                self.assertFalse(dependency.startswith('aixsecurity.adapters'), str(path))

    def test_adapters_do_not_import_delivery_or_composition(self):
        for path in (ROOT / 'adapters').rglob('*.py'):
            for dependency in imports(path):
                self.assertFalse(dependency.startswith(('aixsecurity.entrypoints', 'aixsecurity.composition')), str(path))

    def test_composition_import_has_no_io(self):
        import os
        import subprocess
        import sys
        script = """
from unittest.mock import patch
with patch('sqlite3.connect', side_effect=AssertionError('import opened DB')), \
     patch('socket.socket.connect', side_effect=AssertionError('import opened network')), \
     patch('socket.create_connection', side_effect=AssertionError('import opened network')), \
     patch('subprocess.Popen', side_effect=AssertionError('import started process')):
    import aixsecurity.composition
print('COLD_IMPORT_NO_IO_OK')
"""
        env = dict(os.environ, PYTHONPATH=str(ROOT.parent))
        result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'COLD_IMPORT_NO_IO_OK')
