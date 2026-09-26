"""Synthetic snapshots test only plan contracts, never actual preparation."""
from dataclasses import FrozenInstanceError, replace
import unittest

from aixsecurity.application.planning import PlanningService
from aixsecurity.domain.planning import ScanPlan, ScanSpec, Snapshot, SQLI_CAPABILITIES


def sample(repo='repo-one', snapshot='snapshot-one'):
    return Snapshot(repo, 'a' * 40, snapshot, 'READY', SQLI_CAPABILITIES)


class PlanningTests(unittest.TestCase):
    def test_single_and_multiple_repo_selection(self):
        selected = (sample(), sample('repo-two', 'snapshot-two'))
        spec = PlanningService().create(ScanPlan(), selected)
        self.assertIs(spec.snapshots, selected)
        self.assertEqual(spec.plan.focus, 'sqli')
        self.assertEqual(spec.snapshots[0].commit, 'a' * 40)

    def test_inputs_and_output_are_immutable(self):
        item = sample()
        spec = ScanSpec(ScanPlan(), (item,))
        with self.assertRaises(FrozenInstanceError):
            item.commit = 'b' * 40
        with self.assertRaises(FrozenInstanceError):
            spec.plan = ScanPlan()
        with self.assertRaises(ValueError):
            replace(item, capabilities=set(SQLI_CAPABILITIES))
        with self.assertRaises(ValueError):
            ScanSpec(ScanPlan(), [item])

    def test_not_ready_rejected(self):
        for readiness in ('PARTIAL', 'FAILED', 'PREPARING'):
            with self.subTest(readiness=readiness), self.assertRaisesRegex(ValueError, 'READY'):
                ScanSpec(ScanPlan(), (replace(sample(), readiness=readiness),))

    def test_each_repo_requires_all_capabilities(self):
        for capability in SQLI_CAPABILITIES:
            with self.subTest(capability=capability), self.assertRaisesRegex(ValueError, 'missing capabilities'):
                ScanSpec(ScanPlan(), (replace(sample(), capabilities=SQLI_CAPABILITIES - {capability}),))

    def test_duplicate_repo_or_snapshot_rejected(self):
        for second in (replace(sample(), snapshot_id='second', commit='b' * 40),
                       replace(sample(), repo_id='repo-two')):
            with self.assertRaises(ValueError):
                ScanSpec(ScanPlan(), (sample(), second))

    def test_invalid_or_mutable_references_rejected(self):
        for commit in ('main', 'abc123', 'a' * 39, 'A' * 40, ''):
            with self.subTest(commit=commit), self.assertRaises(ValueError):
                replace(sample(), commit=commit)
        for values in ((), (object(),)):
            with self.assertRaises(ValueError):
                ScanSpec(ScanPlan(), values)

    def test_unknown_mode_not_silently_substituted(self):
        for mode in ('breadth', 'deep', 'unknown'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                ScanPlan(mode=mode)
        with self.assertRaises(ValueError):
            ScanPlan(focus='ssrf')

    def test_snapshot_metadata_validated(self):
        for kwargs in ({'repo_id': ''}, {'snapshot_id': ' spaced '}, {'readiness': 'ready'},
                       {'capabilities': frozenset({''})}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(sample(), **kwargs)


if __name__ == '__main__':
    unittest.main()
