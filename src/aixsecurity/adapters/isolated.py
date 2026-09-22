"""One trusted analyzer subprocess per file, bounded by a wall-clock timeout."""
import json
import subprocess
import sys
from pathlib import Path
from ..domain.models import Finding
from ..ports import WorkerFailure


class IsolatedPythonAnalyzer:
    name = 'python-ast-demo-v1'
    execution_mode = 'subprocess'

    def __init__(self, timeout_seconds=10):
        self.timeout_seconds = timeout_seconds

    def analyze(self, path, source, digest):
        command = [sys.executable, '-I', str(Path(__file__).resolve().parents[1] / 'worker.py')]
        request = json.dumps({'path': path, 'source': source, 'digest': digest}, ensure_ascii=True)
        try:
            # run() kills and waits for the child on TimeoutExpired.
            process = subprocess.run(command, input=request, text=True, encoding='utf-8',
                                     capture_output=True, timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            raise WorkerFailure('WorkerTimeout') from exc
        except UnicodeError as exc:
            raise WorkerFailure('WorkerProtocolError') from exc
        except OSError as exc:
            raise WorkerFailure('WorkerStartError') from exc
        if process.returncode != 0:
            raise WorkerFailure('WorkerCrash')
        try:
            result = json.loads(process.stdout)
            if not isinstance(result, dict):
                raise ValueError('Expected object')
            if set(result) == {'error'} and result['error'] in {'SyntaxError', 'UnicodeError', 'RecursionError'}:
                raise WorkerFailure(result['error'])
            if set(result) != {'findings'} or not isinstance(result['findings'], list):
                raise ValueError('Invalid response shape')
            findings = []
            for item in result['findings']:
                if not isinstance(item, dict):
                    raise ValueError('Invalid finding')
                if (item.get('path') != path or item.get('source_sha256') != digest
                        or type(item.get('line')) is not int or item['line'] < 1
                        or item.get('status') != 'candidate'
                        or item.get('rule_id') != 'PY-DYNAMIC-EXEC'
                        or item.get('evidence_type') != 'static_syntax'
                        or not isinstance(item.get('message'), str)):
                    raise ValueError('Invalid evidence reference')
                finding = Finding(item['rule_id'], path, item['line'], item['message'], digest)
                if finding.to_dict() != item:
                    raise ValueError('Unexpected fields or fingerprint')
                findings.append(finding)
            return findings
        except (ValueError, TypeError, KeyError) as exc:
            raise WorkerFailure('WorkerProtocolError') from exc
