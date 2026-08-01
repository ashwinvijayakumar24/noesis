"""Tests for app/core/logging_config.py.

Two defects were fixed here:

1. ``setup_logging()`` has zero call sites in the repo -- the structured JSON
   logging this project believes it has never ran. Wiring is a later change;
   these tests only prove the formatter is now correct.
2. The production formatter was a hand-rolled ``%``-format template that pasted
   the message between two literal quotes. Any message containing ``"``, a
   newline, or a backslash produced unparseable output. The old template is
   preserved below as a private constant so the regression stays documented.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.logging_config import JsonFormatter, get_logger, setup_logging


# The EXACT production format string as it existed before the fix.
# Kept here so the regression is documented and cannot silently return.
_OLD_BROKEN_FORMAT = (
    '{"time": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", '
    '"function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}'
)

# The message that breaks it: a double quote, a newline, and a backslash --
# i.e. an ordinary exception string or a Windows-ish path in a log line.
HOSTILE_MESSAGE = 'reviewer said "reject"\nreason: bad\\path'


def _record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    return logging.LogRecord(
        name="app.workflows.draft_analysis",
        level=level,
        pathname="/app/workflows/draft_analysis/graph.py",
        lineno=412,
        msg=message,
        args=(),
        exc_info=None,
        func="reviewer_panel_node",
    )


# ---------------------------------------------------------------------------
# The proof that the OLD formatter was broken
# ---------------------------------------------------------------------------

def test_old_formatter_produced_invalid_json():
    """Regression proof: the previous %-template emitted unparseable output."""
    old = logging.Formatter(_OLD_BROKEN_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    output = old.format(_record(HOSTILE_MESSAGE))

    with pytest.raises(json.JSONDecodeError):
        json.loads(output)

    # And concretely why: the quote and newline land in the output raw.
    assert '"reject"' in output
    assert "\n" in output
    assert "bad\\path" in output


@pytest.mark.parametrize(
    "message",
    [
        'has a " quote',
        "has a \n newline",
        "has a \\ backslash",
        "has a \t tab",
    ],
)
def test_old_formatter_broke_on_each_hostile_character(message):
    old = logging.Formatter(_OLD_BROKEN_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    output = old.format(_record(message))
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError:
        return  # unparseable -- defect demonstrated
    # A tab happens to parse, but silently mangles the message rather than
    # preserving it; either way the old formatter is not round-trip safe.
    assert parsed["message"] != message, (
        f"old formatter unexpectedly handled {message!r} correctly"
    )


# ---------------------------------------------------------------------------
# The fixed formatter
# ---------------------------------------------------------------------------

def test_hostile_message_now_parses():
    output = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S").format(_record(HOSTILE_MESSAGE))
    parsed = json.loads(output)  # must not raise
    assert parsed["message"] == HOSTILE_MESSAGE


def test_output_is_exactly_one_line():
    """A newline in the message must not split the record across log lines."""
    output = JsonFormatter().format(_record(HOSTILE_MESSAGE))
    assert "\n" not in output
    assert len(output.splitlines()) == 1


def test_expected_fields_are_present_and_named_as_before():
    output = JsonFormatter(datefmt="%Y-%m-%d %H:%M:%S").format(_record("hello"))
    parsed = json.loads(output)
    assert set(parsed) == {"time", "level", "module", "function", "line", "message"}
    assert parsed["level"] == "INFO"
    assert parsed["module"] == "app.workflows.draft_analysis"
    assert parsed["function"] == "reviewer_panel_node"
    assert parsed["line"] == 412
    assert isinstance(parsed["line"], int)
    assert parsed["message"] == "hello"


def test_level_name_is_carried_through():
    for level, name in [
        (logging.DEBUG, "DEBUG"),
        (logging.WARNING, "WARNING"),
        (logging.ERROR, "ERROR"),
    ]:
        parsed = json.loads(JsonFormatter().format(_record("m", level=level)))
        assert parsed["level"] == name


def test_percent_style_args_are_interpolated():
    record = logging.LogRecord(
        name="n", level=logging.INFO, pathname="p", lineno=1,
        msg='node %s failed: "%s"', args=("reviewer", "timeout"),
        exc_info=None, func="f",
    )
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["message"] == 'node reviewer failed: "timeout"'


def test_non_string_message_does_not_break_serialization():
    parsed = json.loads(JsonFormatter().format(_record({"a": object()})))
    assert isinstance(parsed["message"], str)


def test_exception_info_is_included_and_escaped():
    try:
        raise ValueError('boom "quoted"\nsecond line')
    except ValueError:
        record = logging.LogRecord(
            name="n", level=logging.ERROR, pathname="p", lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(), func="f",
        )
    parsed = json.loads(JsonFormatter().format(record))
    assert "ValueError" in parsed["exception"]
    assert 'boom "quoted"' in parsed["exception"]


# ---------------------------------------------------------------------------
# setup_logging wiring
# ---------------------------------------------------------------------------

BACKEND_ROOT = str(Path(__file__).resolve().parents[1])


def _run_in_subprocess(body: str, env_overrides: dict[str, str]) -> str:
    """Run ``setup_logging()`` in a pristine interpreter and return its stdout.

    ``logging.basicConfig`` no-ops when the root logger already has handlers,
    and pytest's logging plugin attaches its own capture handler around every
    test -- so calling ``setup_logging()`` in-process silently does nothing.
    A subprocess is the only way to assert what it actually configures.
    """
    script = (
        "import sys, logging, json\n"
        f"sys.path.insert(0, {BACKEND_ROOT!r})\n"
        "from app.core.logging_config import setup_logging, get_logger, JsonFormatter\n"
        "setup_logging()\n"
        + body
    )
    env = {**os.environ, **env_overrides}
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True, text=True, env=env, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_setup_logging_respects_log_level():
    out = _run_in_subprocess(
        "print('LEVEL=' + logging.getLevelName(logging.getLogger().level))",
        {"LOG_LEVEL": "warning", "ENVIRONMENT": "production"},
    )
    assert "LEVEL=WARNING" in out


def test_setup_logging_uses_json_formatter_in_production():
    out = _run_in_subprocess(
        "h = logging.getLogger().handlers\n"
        "print('COUNT=%d' % len(h))\n"
        "print('JSON=%s' % isinstance(h[0].formatter, JsonFormatter))\n",
        {"LOG_LEVEL": "INFO", "ENVIRONMENT": "production"},
    )
    assert "COUNT=1" in out
    assert "JSON=True" in out


def test_setup_logging_uses_plain_formatter_in_development():
    out = _run_in_subprocess(
        "f = logging.getLogger().handlers[0].formatter\n"
        "print('JSON=%s' % isinstance(f, JsonFormatter))\n"
        "print('FMT=%s' % isinstance(f, logging.Formatter))\n",
        {"LOG_LEVEL": "INFO", "ENVIRONMENT": "development"},
    )
    assert "JSON=False" in out
    assert "FMT=True" in out


def test_setup_logging_quiets_noisy_third_party_loggers():
    out = _run_in_subprocess(
        "for n in ('httpx', 'httpcore', 'urllib3'):\n"
        "    print(n + '=' + logging.getLevelName(logging.getLogger(n).level))\n",
        {"ENVIRONMENT": "production"},
    )
    assert "httpx=WARNING" in out
    assert "httpcore=WARNING" in out
    assert "urllib3=WARNING" in out


def test_production_logging_end_to_end_is_parseable():
    out = _run_in_subprocess(
        f"get_logger('app.core.test').info({HOSTILE_MESSAGE!r})\n",
        {"LOG_LEVEL": "INFO", "ENVIRONMENT": "production"},
    )
    line = out.strip()
    # One line, despite the newline inside the message.
    assert len(line.splitlines()) == 1
    assert json.loads(line)["message"] == HOSTILE_MESSAGE


def test_production_logging_end_to_end_would_have_broken_before():
    """Same run through the OLD template: unparseable, and split across lines."""
    old = logging.Formatter(_OLD_BROKEN_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    output = old.format(_record(HOSTILE_MESSAGE))
    assert len(output.splitlines()) == 2
    with pytest.raises(json.JSONDecodeError):
        json.loads(output)


def test_setup_logging_still_has_no_call_sites_in_app_code():
    """Scope guard: wiring setup_logging() is a later change, not this one."""
    app_root = Path(__file__).resolve().parents[1] / "app"
    offenders = [
        str(py)
        for py in app_root.rglob("*.py")
        if py.name != "logging_config.py"
        and "setup_logging" in py.read_text(encoding="utf-8", errors="ignore")
    ]
    assert offenders == [], f"unexpected setup_logging call sites: {offenders}"
