import time

from agent.analysis.test_output_parser import PytestResult
from agent.config import Config
from agent.core.state import AgentState
from agent.core.stopping_criteria import check_stop
from agent.utils.cost_tracker import CostTracker


def failing(scope="targeted"):
    return PytestResult(exit_code=1, failed=1, scope=scope,
                        failures=[{"name": "t", "error": ["E boom"], "locations": []}])


def passing(scope="full"):
    return PytestResult(exit_code=0, passed=3, scope=scope)


def setup():
    cfg = Config()
    return AgentState(), CostTracker(cfg), cfg, time.time()


def test_finished():
    state, cost, cfg, t0 = setup()
    state.finished = True
    assert check_stop(state, cost, cfg, t0).reason == "agent_finished"


def test_max_steps():
    state, cost, cfg, t0 = setup()
    state.step = cfg.max_steps
    assert check_stop(state, cost, cfg, t0).reason == "max_steps"


def test_max_cost():
    state, cost, cfg, t0 = setup()
    cost.output_tokens = 10_000_000
    assert check_stop(state, cost, cfg, t0).reason == "max_cost"


def test_stuck_after_repeated_identical_failures():
    state, cost, cfg, t0 = setup()
    for _ in range(cfg.stuck_threshold * 2):
        state.record_test(failing())
    assert check_stop(state, cost, cfg, t0).reason == "stuck"


def test_verified_requires_reproduction_then_full_pass_after_edit():
    state, cost, cfg, t0 = setup()
    state.record_test(failing("targeted"))        # reproduction
    state.record_edit("src/x.py", "str_replace")
    state.record_test(passing("full"))
    assert check_stop(state, cost, cfg, t0).reason == "verified"


def test_not_verified_without_reproduction():
    state, cost, cfg, t0 = setup()
    state.record_edit("src/x.py", "str_replace")
    state.record_test(passing("full"))
    assert not check_stop(state, cost, cfg, t0).stop


def test_not_verified_if_edit_after_full_pass():
    state, cost, cfg, t0 = setup()
    state.record_test(failing("targeted"))
    state.record_edit("src/x.py", "str_replace")
    state.record_test(passing("full"))
    state.record_edit("src/x.py", "str_replace")   # new edit invalidates the pass
    assert not state.verified()