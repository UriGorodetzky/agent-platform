"""Tests for the structured logging helpers."""

import json
import logging

from orchestrator.logging_config import JsonFormatter, RunIdFilter, run_id_var


def make_record(msg="hello %s", args=("world",)):
    return logging.LogRecord(
        name="orchestrator.test", level=logging.INFO, pathname="", lineno=0,
        msg=msg, args=args, exc_info=None,
    )


def test_formatter_emits_json_with_core_fields():
    out = json.loads(JsonFormatter().format(make_record()))
    assert out["level"] == "INFO"
    assert out["logger"] == "orchestrator.test"
    assert out["msg"] == "hello world"        # %-args are rendered
    assert "ts" in out
    assert out["run_id"] == "-"               # nothing set -> placeholder


def test_formatter_includes_extra_fields():
    record = make_record(msg="agent done", args=())
    record.agent = "echo-1"                   # an "extra" field
    record.attempt = 2
    out = json.loads(JsonFormatter().format(record))
    assert out["agent"] == "echo-1"
    assert out["attempt"] == 2


def test_filter_injects_run_id_from_contextvar():
    token = run_id_var.set("run-xyz")
    try:
        record = make_record(msg="x", args=())
        RunIdFilter().filter(record)
        assert record.run_id == "run-xyz"
        out = json.loads(JsonFormatter().format(record))
        assert out["run_id"] == "run-xyz"
    finally:
        run_id_var.reset(token)
