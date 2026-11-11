import unittest
from app.facts import extract_candidates
class FactTests(unittest.TestCase):
    def test_locator_and_unconfirmed_status_retained(self):
        result=extract_candidates([{'page':2,'text':'型号：A\n颜色: 白色\n广告句子'}],'source')
        self.assertEqual(len(result),2)
        self.assertEqual(result[0]['locator'],{'source_id':'source','page':2})
        self.assertEqual(result[0]['status'],'candidate')
        self.assertEqual(result[1]['value'],'白色')
    def test_whitespace_only_key_or_value_is_not_a_fact(self):
        self.assertEqual(extract_candidates([{'paragraph':1,'text':'  : value\n型号:   \n = '}],'source'),[])
