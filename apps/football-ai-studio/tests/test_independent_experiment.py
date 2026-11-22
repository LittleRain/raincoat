import pytest
from scripts.validate_minimax_video import estimate_cny, validate_result


def test_cost_is_equivalent_and_does_not_double_charge_cached_input():
    assert estimate_cny({'prompt_tokens':8153,'completion_tokens':283,'prompt_tokens_details':{'cached_tokens':142}})==0.01925994
    assert estimate_cny({'prompt_tokens':1000,'completion_tokens':0,'prompt_tokens_details':{'cached_tokens':1000}})==.00042
    assert estimate_cny({}) is None


@pytest.mark.parametrize('change',[{'end_s':23},{'identity_status':'confirmed_target'},{'event_confidence':float('nan')},{'start_s':True}])
def test_experiment_rejects_invalid_time_or_unearned_confirmation(change):
    event={'start_s':1,'end_s':3,'event_type':'shot','identity_status':'likely_target',
           'event_confidence':.5,'identity_confidence':.5}
    event.update(change)
    with pytest.raises(ValueError):
        validate_result({'events':[event]},22.146667)
