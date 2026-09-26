"""Pure validation for repository registration; no network or DNS resolution."""
from __future__ import annotations

import ipaddress
import unicodedata
from urllib.parse import unquote, urlsplit, urlunsplit


def clean_text(value: str, field: str, maximum: int = 200) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError(f"{field} must be text without control characters")
    value = value.strip()
    if not value or len(value) > maximum:
        raise ValueError(f"{field} must contain 1..{maximum} characters")
    return value


def normalize_repository(value: str) -> str:
    """Canonical HTTPS identifier, not a fetch authorization or DNS safety check.

    A future fetch adapter must resolve and check every address/redirect itself.
    Credentials must be passed separately, never embedded in asset identifiers.
    """
    value = clean_text(value, "repository", 2048)
    if any(c.isspace() for c in value) or any(c in value for c in ('\\', '?', '#')):
        raise ValueError("repository URL must not contain whitespace, query, fragment or backslash")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise ValueError("invalid repository URL") from exc
    if parsed.scheme != 'https' or not host or parsed.username is not None or parsed.password is not None:
        raise ValueError("repository must be an HTTPS URL without user information")
    host = host.rstrip('.').lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        try:
            host = host.encode('idna').decode('ascii')
        except UnicodeError as exc:
            raise ValueError("invalid repository host") from exc
        labels = host.split('.')
        if (len(labels) < 2 or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid'))
                or not any(c.isalpha() for c in labels[-1])
                or any(not label or len(label) > 63 or label.startswith('-') or label.endswith('-')
                       or not all(c.isalnum() or c == '-' for c in label) for label in labels)):
            raise ValueError("repository host must be a public-style DNS name")
    else:
        if not address.is_global:
            raise ValueError("repository IP address must be public")
        host = f'[{address.compressed}]' if address.version == 6 else address.compressed
    if port is not None and port < 1:
        raise ValueError("repository port must be positive")
    decoded_path = unquote(parsed.path)
    if (not parsed.path or parsed.path == '/' or '\\' in decoded_path
            or any(c.isspace() or unicodedata.category(c).startswith('C') for c in decoded_path)
            or any(segment in ('.', '..') for segment in decoded_path.split('/'))):
        raise ValueError("repository URL must contain a valid repository path")
    netloc = host if port in (None, 443) else f'{host}:{port}'
    return urlunsplit(('https', netloc, parsed.path.rstrip('/'), '', ''))


def normalize_registration(name: str, repositories: list[str], idempotency_key: str) -> tuple[str, list[str], str]:
    name = clean_text(name, 'name')
    key = clean_text(idempotency_key, 'idempotency_key')
    if not isinstance(repositories, list) or not 1 <= len(repositories) <= 100:
        raise ValueError('repositories must be a list containing 1..100 URLs')
    urls = [normalize_repository(value) for value in repositories]
    if len(set(urls)) != len(urls):
        raise ValueError('duplicate repository URL')
    return name, urls, key
