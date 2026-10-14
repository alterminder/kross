import pytest

from nlab.engine import EngineError, start, time_up


def test_time_up_ends_the_session_as_a_failure_or_without_a_result(scenario, rules):
    begun = start(scenario("s01_idp_camp_access"), rules).state
    failed = time_up(begun, fail=True)
    assert (failed.state.outcome.id, failed.state.outcome.result) == ("time_up", "fail")
    assert failed.state.outcome.label == "Time ran out without an agreement"
    assert [(e.kind, e.ref) for e in failed.events] == [("outcome", "time_up")]
    plain = time_up(begun, fail=False)
    assert (plain.state.outcome.result, plain.state.outcome.label) == ("ended", "Time ran out")
    assert begun.outcome is None  # the old state is untouched
    with pytest.raises(EngineError):
        time_up(failed.state, fail=True)
