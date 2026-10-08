from agent.analysis.test_output_parser import parse_pytest_output

FAILED_OUTPUT = """\
=================================== FAILURES ===================================
______________________________ test_add ______________________________

    def test_add():
>       assert add(1, 2) == 4
E       assert 3 == 4
E        +  where 3 = add(1, 2)

tests/test_math.py:3: AssertionError
=========================== short test summary info ============================
FAILED tests/test_math.py::test_add - assert 3 == 4
1 failed, 1 passed in 0.02s
"""


def test_parses_failure():
    res = parse_pytest_output(FAILED_OUTPUT, exit_code=1)
    assert not res.ok
    assert res.failed == 1 and res.passed == 1
    assert res.failures[0]["name"] == "test_add"
    assert "assert 3 == 4" in res.failures[0]["error"][0]
    assert res.failures[0]["locations"][0].startswith("tests/test_math.py:3")


def test_passing_run():
    res = parse_pytest_output("..\n2 passed in 0.01s\n", exit_code=0)
    assert res.ok and res.passed == 2 and res.signature() == "ok"


def test_signature_stable_for_same_failure():
    a = parse_pytest_output(FAILED_OUTPUT, 1)
    b = parse_pytest_output(FAILED_OUTPUT, 1)
    assert a.signature() == b.signature() != "ok"