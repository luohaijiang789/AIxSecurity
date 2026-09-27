"""Local OpenAI-compatible proxy client. No SDK, redirects, or automatic retries."""
from dataclasses import dataclass, field
import json
import http.client
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request


class ModelError(ValueError):
    """Sanitized model configuration/transport/protocol failure."""


@dataclass(frozen=True)
class ModelConfig:
    base_url: str
    model: str
    api_key: str = field(repr=False)

    def __post_init__(self):
        if not all(isinstance(v, str) for v in (self.base_url, self.model, self.api_key)):
            raise ModelError('Model configuration values must be strings')
        try:
            parsed = urllib.parse.urlsplit(self.base_url)
        except ValueError:
            raise ModelError('Invalid local proxy URL') from None
        if (parsed.scheme != 'http' or parsed.hostname not in ('localhost', '127.0.0.1', '::1')
                or parsed.username is not None or parsed.password is not None
                or parsed.path.rstrip('/') != '/v1' or parsed.query or parsed.fragment):
            raise ModelError('Expected local HTTP proxy URL ending in /v1')
        try:
            parsed.port
        except ValueError:
            raise ModelError('Invalid proxy port') from None
        if not self.model.strip() or not self.api_key.strip() or any(not 33 <= ord(c) <= 126 for c in self.api_key):
            raise ModelError('Model name and valid API key are required')


def load_config(path=Path('.env'), *, environ=None):
    """Explicit KEY=value file; no shell expansion. Environment overrides file."""
    names = ('AIXSECURITY_MODEL_BASE_URL', 'AIXSECURITY_MODEL_NAME', 'AIXSECURITY_MODEL_API_KEY')
    values = {}
    path = Path(path)
    if path.exists():
        if path.is_symlink() or not path.is_file():
            raise ModelError('Model config must be a regular file')
        if path.stat().st_mode & 0o077:
            raise ModelError('Model config permissions must be 0600')
        try:
            raw = path.read_text()
        except UnicodeError:
            raise ModelError('Model configuration must be UTF-8 text') from None
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith('#'):
                continue
            key, separator, value = line.partition('=')
            if not separator:
                raise ModelError('Expected KEY=value model configuration')
            if key.strip() in names:
                values[key.strip()] = value.strip()
    env = os.environ if environ is None else environ
    values.update({key: env[key] for key in names if key in env})
    if not all(values.get(key) for key in names):
        raise ModelError('Model configuration is incomplete')
    return ModelConfig(values[names[0]].rstrip('/'), values[names[1]], values[names[2]])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class LocalModelClient:
    """timeout limits blocking network operations, not total wall-clock duration."""
    def __init__(self, config, *, opener=None, timeout=30):
        if not isinstance(config, ModelConfig):
            raise ModelError('Expected ModelConfig')
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 120:
            raise ModelError('Timeout must be between 0 and 120 seconds')
        self.config = config
        self.timeout = timeout
        self.opener = opener or urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect())

    def _request(self, endpoint, payload=None):
        body = None if payload is None else json.dumps(payload).encode()
        request = urllib.request.Request(self.config.base_url + endpoint, data=body,
            headers={'Authorization': 'Bearer ' + self.config.api_key,
                     'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(1_048_577)
            if len(raw) > 1_048_576:
                raise ModelError('Proxy response exceeds size limit')
            result = json.loads(raw)
        except ModelError:
            raise
        except urllib.error.HTTPError as exc:
            # Neither response body nor request headers may enter diagnostics.
            status = exc.code
            exc.close()
            raise ModelError(f'Proxy HTTP status {status}') from None
        except (urllib.error.URLError, TimeoutError, OSError):
            raise ModelError('Local proxy connection failed or timed out') from None
        except (ValueError, UnicodeError, RecursionError, http.client.HTTPException):
            raise ModelError('Invalid proxy JSON response') from None
        if not isinstance(result, dict) or 'error' in result:
            raise ModelError('Proxy returned an invalid or error response')
        return result

    def list_models(self):
        result = self._request('/models')
        data = result.get('data')
        if not isinstance(data, list):
            raise ModelError('Proxy model list is missing')
        return [row['id'] for row in data if isinstance(row, dict) and isinstance(row.get('id'), str)]

    def complete(self, messages, *, max_tokens=128, json_mode=False):
        if type(max_tokens) is not int or not 1 <= max_tokens <= 4096:
            raise ModelError('max_tokens must be 1..4096')
        if not isinstance(messages, list) or not messages or len(messages) > 32:
            raise ModelError('Expected 1..32 messages')
        if any(not isinstance(m, dict) or set(m) != {'role', 'content'}
               or m['role'] not in ('system', 'user', 'assistant')
               or not isinstance(m['content'], str) for m in messages):
            raise ModelError('Invalid chat message')
        if sum(len(m['content']) for m in messages) > 32768:
            raise ModelError('Message budget exceeded')
        if type(json_mode) is not bool:
            raise ModelError('json_mode must be boolean')
        payload = {'model': self.config.model, 'messages': messages,
                   'max_tokens': max_tokens, 'stream': False}
        if json_mode: payload['response_format'] = {'type': 'json_object'}
        result = self._request('/chat/completions', payload)
        try:
            choice = result['choices'][0]
            content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelError('Proxy returned no text completion') from None
        if json_mode and choice.get('finish_reason') == 'length':
            raise ModelError('Structured response exceeded token budget')
        return {'content': content, 'model': result.get('model', self.config.model),
                'finish_reason': choice.get('finish_reason'), 'usage': result.get('usage')}

    def smoke_test(self):
        models = self.list_models()
        if self.config.model not in models:
            raise ModelError('Configured model is absent from proxy model list')
        result = self.complete([{'role': 'user', 'content': 'Reply with exactly AIXSECURITY_OK.'}], max_tokens=32)
        matched = result['content'].strip() == 'AIXSECURITY_OK'
        # Never echo arbitrary provider content or metadata in health diagnostics.
        return {'status': 'ok' if matched else 'unexpected_reply',
                'endpoint': '/v1/chat/completions', 'requested_model': self.config.model,
                'model_listed': True, 'reply_matches': matched,
                'project_source_sent': False}
