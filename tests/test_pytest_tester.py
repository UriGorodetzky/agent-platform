"""Tests for the PytestTesterAgent — it runs real pytest in a workspace."""

from orchestrator.agents import PytestTesterAgent
from orchestrator.models import Task, TaskStatus


def task(workspace) -> Task:
    return Task(type="testing", prompt="run tests", context={"workspace": str(workspace)})


async def test_passing_tests_report_success(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert 1 + 1 == 2\n")
    result = await PytestTesterAgent().execute(task(tmp_path))
    assert result.status is TaskStatus.SUCCESS


async def test_failing_tests_report_failure(tmp_path):
    (tmp_path / "test_bad.py").write_text("def test_bad():\n    assert False\n")
    result = await PytestTesterAgent().execute(task(tmp_path))
    assert result.status is TaskStatus.FAILURE
    assert "assert" in result.output.lower()      # the failure detail is captured


async def test_no_tests_is_a_failure(tmp_path):
    result = await PytestTesterAgent().execute(task(tmp_path))
    assert result.status is TaskStatus.FAILURE     # pytest exits non-zero (no tests collected)
