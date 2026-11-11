import pytest
from marketing_worker.business import validate_hailuo_shots
from marketing_worker.pipeline import ContractError

def data(durations):
    return {'douyin':{'title':'a','body':'a','narration':'a','poster_title':'a','shots':[{'duration':d,'narration':'a','fact_refs':['f']} for d in durations]}}

def test_single_shot_accepted():
    validate_hailuo_shots(data([5]),{'duration_seconds':5,'platforms':['douyin'],'facts':[{'id':'f','validity':'active'}]})

@pytest.mark.parametrize('durations',[[2,3],[7,1]])
def test_unquoted_billable_shots_rejected(durations):
    with pytest.raises(ContractError,match='quoted_shot_count_mismatch'):
        validate_hailuo_shots(data(durations),{'duration_seconds':sum(durations),'platforms':['douyin'],'facts':[{'id':'f','validity':'active'}]})
