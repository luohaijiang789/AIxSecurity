"""Thin CLI: parse commands, invoke use cases, format results; no business SQL."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from .. import __version__
from ..composition import build_application, check_environment, check_model, read_legacy_runs


def _parser():
    parser = argparse.ArgumentParser(prog='aixsecurity',
        description='Java security audit modular foundation; analysis pipeline pending')
    parser.add_argument('--version', action='version', version=__version__)
    sub = parser.add_subparsers(dest='command', required=True)
    doctor = sub.add_parser('doctor', help='Check local prerequisites')
    doctor.add_argument('--env-file', type=Path, default=Path('.env'))
    doctor.add_argument('--defer-model', action='store_true')
    model = sub.add_parser('model-check', help='Check local model without project source')
    model.add_argument('--env-file', type=Path, default=Path('.env'))
    runs = sub.add_parser('runs', help='Inspect legacy run records')
    runs.add_argument('--ledger', type=Path, default=Path('runs/ledger.sqlite3'))
    actions = runs.add_subparsers(dest='action', required=True)
    actions.add_parser('list')
    actions.add_parser('show').add_argument('run_id')
    assets = sub.add_parser('assets', help='Register and inspect the persistent asset catalog')
    assets.add_argument('--database', type=Path, default=Path('runs/platform.sqlite3'))
    actions = assets.add_subparsers(dest='action', required=True)
    register = actions.add_parser('register', help='Atomically register repositories and queue preparation')
    register.add_argument('--name', required=True)
    register.add_argument('--repo', action='append', required=True, dest='repositories')
    register.add_argument('--request-id', required=True, help='Idempotency key for this registration')
    actions.add_parser('list')
    actions.add_parser('show').add_argument('project_id')
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == 'doctor':
            result = check_environment(args.env_file, args.defer_model)
            code = 2 if result['blockers'] else 0
        elif args.command == 'model-check':
            result = check_model(args.env_file)
            code = 0 if result['status'] == 'ok' else 2
        elif args.command == 'runs':
            result = read_legacy_runs(args.ledger, args.run_id if args.action == 'show' else None)
            code = 0
        else:
            # Read commands must not create an empty database as a side effect.
            if args.action != 'register' and not args.database.is_file():
                raise ValueError('Asset database does not exist; register a project first')
            with build_application(args.database, read_only=args.action != 'register') as app:
                if args.action == 'register':
                    result = app.assets.register(args.name, args.repositories, args.request_id)
                elif args.action == 'list':
                    result = app.assets.list()
                else:
                    result = app.assets.get(args.project_id)
            code = 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
    except (OSError, sqlite3.Error):
        # OS/library errors may contain paths or configuration; expose a stable boundary.
        print('Local storage or configuration operation failed.', file=sys.stderr)
    return 2
