import copy
import pytest
from marketing_worker.fact_validation import repair_missing_global_refs,validate_numeric_claims,NumericFactError,visual_numeric_text
from marketing_worker.pipeline import validate_copy
FACTS=[{'id':k,'value':v,'validity':'active'} for k,v in {'name':'华为耳机','model':'001','color':'8*5*2','merchant_sku':'001','specification':'8*5*2'}.items()]

def fixture():
    return {'douyin':{'title':'华为耳机001','body':'华为耳机，型号001，规格8*5*2。','narration':'看看华为耳机','poster_title':'华为耳机001','selling_points':['型号001'],'shots':[{'duration':6,'narration':'看看华为耳机','fact_refs':['name','model'],'visual_description':'9:16 Studio 暖灰背景'}]}}

def test_exact_reported_fixture_passes_with_audited_refs_only():
    original=fixture();request={'platforms':['douyin'],'duration_seconds':6,'facts':FACTS}
    result,changes=repair_missing_global_refs(original,request)
    assert 'fact_refs' not in original['douyin']
    assert changes[0]['rule']=='exact_active_fact_value_v1'
    assert 'model' in result['douyin']['fact_refs'] and 'specification' in result['douyin']['fact_refs']
    assert validate_copy(result,request)==result

@pytest.mark.parametrize('claim',['8*5*20','8*5*2厘米','8*5*2英寸','续航9小时','型号0010','型号A001'])
def test_unconfirmed_numeric_extensions_remain_blocked(claim):
    with pytest.raises(NumericFactError):validate_numeric_claims(claim,[f['id'] for f in FACTS],{f['id']:f for f in FACTS})

def test_refs_not_added_by_substring_or_revoked_facts():
    result,changes=repair_missing_global_refs({'douyin':{'title':'型号0010','body':'暂无','selling_points':[]}}, {'facts':[FACTS[1],{'id':'other','value':'0010','validity':'revoked'}]})
    assert not changes and 'fact_refs' not in result['douyin']

def test_explicit_bad_refs_are_not_overridden():
    item=fixture();item['douyin']['fact_refs']=['unknown']
    result,changes=repair_missing_global_refs(item,{'facts':FACTS})
    assert not changes and result==item

@pytest.mark.parametrize('text',['9:16 Studio 续航9小时','画幅9:16 续航10小时','9:160 Studio','规格9:16厘米','屏幕9:16','屏幕9:16 Studio'])
def test_frame_ratio_does_not_hide_product_claims(text):
    with pytest.raises(NumericFactError):validate_numeric_claims(visual_numeric_text(text),[],{})
