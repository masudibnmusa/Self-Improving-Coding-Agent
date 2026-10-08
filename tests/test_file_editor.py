from agent.config import Config
from agent.core.state import AgentState
from agent.tools.file_editor import create_file, str_replace_edit
from agent.tools.registry import ToolContext


def make_ctx(tmp_path):
    return ToolContext(repo_path=tmp_path, sandbox=None, state=AgentState(), config=Config())


def test_unique_replace(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    out = str_replace_edit(make_ctx(tmp_path), "a.py", "x = 1", "x = 10")
    assert not out.startswith("ERROR")
    assert (tmp_path / "a.py").read_text() == "x = 10\ny = 2\n"


def test_not_found(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    assert str_replace_edit(make_ctx(tmp_path), "a.py", "z = 9", "z = 1").startswith("ERROR")


def test_multiple_matches_rejected(tmp_path):
    (tmp_path / "a.py").write_text("x\nx\n")
    out = str_replace_edit(make_ctx(tmp_path), "a.py", "x", "y")
    assert out.startswith("ERROR") and "2 times" in out


def test_syntax_error_rejected_and_file_unchanged(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    out = str_replace_edit(make_ctx(tmp_path), "a.py", "x = 1", "x = (")
    assert out.startswith("ERROR")
    assert (tmp_path / "a.py").read_text() == "x = 1\n"


def test_test_files_are_protected(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("def test_a():\n    assert True\n")
    out = str_replace_edit(make_ctx(tmp_path), "tests/test_a.py", "True", "False")
    assert out.startswith("ERROR")


def test_repro_files_allowed(tmp_path):
    out = create_file(make_ctx(tmp_path), "repro_bug.py", "def test_x():\n    assert False\n")
    assert not out.startswith("ERROR")
    assert (tmp_path / "repro_bug.py").exists()


def test_path_escape_blocked(tmp_path):
    assert create_file(make_ctx(tmp_path), "../evil.py", "x = 1\n").startswith("ERROR")