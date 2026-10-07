"""Ranking language boundaries and real subprocess execution, with no providers."""
import os
import sys
import unittest
from pathlib import Path
assert os.environ.get('RALLY_TESTING')=='1'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import algorithm_worker as worker
import algorithms
import service as s

class Ranking(unittest.TestCase):
    def features(self,**values):return {**dict.fromkeys(worker.FEATURES,0),**values}
    def test_formula_runs_in_the_actual_child(self):
        scores,elapsed=algorithms.run('recency + likes * 2',[{'id':'one','features':self.features(recency=2,likes=3)}])
        self.assertEqual(scores,[{'id':'one','score':8.0}]);self.assertGreaterEqual(elapsed,0)
    def test_conditions(self):
        tree=worker.parse('likes if following and has_media else -1')
        self.assertEqual(worker.evaluate(tree,self.features(likes=4,following=1,has_media=1)),4)
    def test_python_capabilities_are_rejected(self):
        for formula in ["__import__('os')","likes.real","[likes]","likes[0]","lambda: 1","2 ** 5","open('/etc/passwd')","unknown_feature"]:
            with self.subTest(formula=formula),self.assertRaises(ValueError):worker.parse(formula)
    def test_length_node_depth_and_numeric_limits(self):
        for formula in ['1'*1001,'+'.join(['1']*100),'1e999','1000001','-'*30+'1']:
            with self.subTest(formula=formula),self.assertRaises(ValueError):worker.parse(formula)
    def test_division_and_nonfinite_output_rejected(self):
        with self.assertRaises(ValueError):worker.evaluate(worker.parse('likes / recency'),self.features())
        with self.assertRaises(s.Problem):algorithms.run('likes * likes * likes',[{'id':'one','features':self.features(likes=1000000)}])
    def test_candidate_and_feature_bounds(self):
        for items in [[{'id':'one','features':{}}],[{'id':str(i),'features':self.features()} for i in range(101)]]:
            with self.assertRaises(s.Problem):algorithms.run('recency',items)

if __name__=='__main__':unittest.main()
