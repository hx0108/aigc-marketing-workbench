import unittest
from marketing_worker.fact_validation import validate_numeric_claims,NumericFactError


class NumericTests(unittest.TestCase):
    def test_exact_referenced_model_identifier(self):
        facts={'model':{'value':'A1','validity':'active'}}
        validate_numeric_claims('型号A1适合桌面',['model'],facts)
        validate_numeric_claims('型号Ａ１',['model'],facts)
        for text in ('型号A2','型号A10','型号XA1'):
            with self.subTest(text=text),self.assertRaises(NumericFactError):validate_numeric_claims(text,['model'],facts)

    def test_sku_number_cannot_erase_power_claim(self):
        facts={'merchant_sku':{'value':'200','validity':'active'}}
        with self.assertRaisesRegex(NumericFactError,'NUMERIC_FACT_MISMATCH'):
            validate_numeric_claims('功率200W',['merchant_sku'],facts)
        facts['merchant_sku']['value']='200W'
        with self.assertRaisesRegex(NumericFactError,'NUMERIC_FACT_MISMATCH'):
            validate_numeric_claims('功率200W',['merchant_sku'],facts)

    def test_nfkc_and_unit_boundaries(self):
        facts={'power':{'value':'20W','validity':'active'},'temperature':{'value':'20℃','validity':'active'}}
        validate_numeric_claims('功率２０Ｗ，温度20°C',['power','temperature'],facts)
        with self.assertRaises(NumericFactError):validate_numeric_claims('20Wh',['power'],facts)
    facts={'capacity':{'value':'500毫升','validity':'active'},'weight':{'value':'200克','validity':'active'},'power':{'value':'20W','validity':'active'}}
    def test_confirmed_unit_conversion(self):
        validate_numeric_claims('容量0.5L，重量0.2kg',['capacity','weight'],self.facts)
    def test_invented_quantity_rejected(self):
        with self.assertRaisesRegex(NumericFactError,'NUMERIC_FACT_MISMATCH'):
            validate_numeric_claims('功率200W',['power'],self.facts)
    def test_valid_id_cannot_hide_wrong_reference(self):
        with self.assertRaisesRegex(NumericFactError,'NUMERIC_FACT_MISMATCH'):
            validate_numeric_claims('容量500毫升',['weight'],self.facts)
    def test_unsupported_number_waits_for_confirmation(self):
        with self.assertRaisesRegex(NumericFactError,'REVIEW_REQUIRED'):
            validate_numeric_claims('续航三小时，等级IP68',['capacity'],self.facts)
