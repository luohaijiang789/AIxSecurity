"""Versioned capability contracts are independent of HTTP and persistence."""
import unittest
from dataclasses import FrozenInstanceError
from aixsecurity.domain.profiles import DEFAULT_PROFILE, get_profile, list_profiles, candidate_category


class ProfilesTests(unittest.TestCase):
    def test_catalog_is_immutable_and_public_fields_are_isolated(self):
        rows = list_profiles(); self.assertEqual(len(rows), 3)
        rows[0]['title'] = 'changed'
        self.assertEqual(get_profile(DEFAULT_PROFILE).title, 'SQL 注入')
        self.assertNotIn('review_focus', rows[0])
        with self.assertRaises(FrozenInstanceError):
            get_profile().title = 'changed'

    def test_unknown_profiles_never_fall_back_to_sqli(self):
        for value in ('unknown', '', None, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                get_profile(value)

    def test_only_known_matching_categories_are_selected(self):
        self.assertEqual(candidate_category({'rule_id':'prefix.aix.java.sqli.taint'}), 'sqli')
        self.assertIsNone(candidate_category({'rule_id':'other.rule'}))
        self.assertIsNone(candidate_category({'rule_id':'aix.java.sqli.taint','category':'path-traversal'}))
