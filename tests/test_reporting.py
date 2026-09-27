import unittest
from aixsecurity.application.reporting import render_markdown


class ReportingTests(unittest.TestCase):
    def test_report_preserves_partial_and_unreviewed(self):
        report={'snapshot_id':'abc','plan':'sqli-intraprocedural-v1','coverage':'partial',
                'summary':{'candidate_count':5,'attempted':1,'reviewed':0},
                'findings':[{'id':'one','status':'suspicious','path':'Demo.java','line':4,'verification_method':'unreviewed','reason':'model unavailable'}],
                'limitations':['No path proof'],'repositories':[]}
        text=render_markdown(report)
        self.assertIn('partial',text);self.assertIn('unreviewed',text)
        self.assertIn('No path proof',text);self.assertNotIn('confirmed',text)
