"""Offline synthetic registrations; these URLs are never fetched."""
import unittest
from unittest.mock import Mock

from aixsecurity.application.assets import AssetService
from aixsecurity.domain.assets import normalize_registration, normalize_repository


class AssetServiceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Mock()
        self.service = AssetService(self.catalog)

    def test_register_normalizes_and_calls_port_once(self):
        self.catalog.register.return_value = {'project_id': 'synthetic-project'}
        result = self.service.register(' Demo ', ['https://EXAMPLE.com:443/team/repo/'], ' key ')
        self.assertEqual(result['project_id'], 'synthetic-project')
        self.catalog.register.assert_called_once_with('Demo', ['https://example.com/team/repo'], 'key')

    def test_rejects_bad_urls_before_port(self):
        urls = ['http://example.com/a', 'file:///tmp/a', 'https://user:pw@example.com/a',
                'https://example.com/a?token=x', 'https://example.com/a#x', 'https://localhost/a',
                'https://127.0.0.1/a', 'https://10.0.0.1/a', 'https://[::1]/a',
                'https://service.internal/a', 'https://example.com/../a',
                'https://example.com/%2e%2e/a', 'https://example.com/a\n',
                'https://example.com/%00a', 'https://example.com/a b', 'https://example.com/',
                'https://2130706433/a', 'https://127.1/a', 'https://example.com:99999/a']
        for url in urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.service.register('demo', [url], 'key')
        self.catalog.register.assert_not_called()

    def test_rejects_duplicates_after_normalization(self):
        with self.assertRaises(ValueError):
            self.service.register('demo', ['https://EXAMPLE.com:443/a/', 'https://example.com/a'], 'key')
        self.catalog.register.assert_not_called()

    def test_text_and_collection_validation(self):
        for name, repos, key in [('', ['https://example.com/a'], 'x'),
                                 ('demo', [], 'x'), ('demo', 'https://example.com/a', 'x'),
                                 ('demo', ['https://example.com/a'], ''),
                                 ('demo\x00', ['https://example.com/a'], 'x')]:
            with self.subTest(name=name, repos=repos, key=key), self.assertRaises(ValueError):
                normalize_registration(name, repos, key)

    def test_registration_is_copied_not_mutated(self):
        original = ['https://EXAMPLE.com/a/']
        _, result, _ = normalize_registration('demo', original, 'key')
        self.assertEqual(original, ['https://EXAMPLE.com/a/'])
        self.assertIsNot(original, result)

    def test_public_ipv6_format_and_unicode_host(self):
        self.assertEqual(normalize_repository('https://[2606:4700:4700::1111]/a'),
                         'https://[2606:4700:4700::1111]/a')
        self.assertEqual(normalize_repository('https://例子.com/a'), 'https://xn--fsqu00a.com/a')

    def test_list_and_get_delegate_and_validate(self):
        self.service.list()
        self.catalog.list_projects.assert_called_once_with()
        self.service.get(' project ')
        self.catalog.get_project.assert_called_once_with('project')
        with self.assertRaises(ValueError):
            self.service.get('')


if __name__ == '__main__':
    unittest.main()
