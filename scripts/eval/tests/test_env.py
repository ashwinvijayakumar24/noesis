"""The eval harness runs on the host and never sees what compose injects into the
backend container, so a credential sitting in services/backend/.env was silently
invisible. The failure was quiet: OpenAlex simply ran on the $0.10/day
unauthenticated tier instead of the $1.00/day authenticated one, with no error.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest


def _load_env_module():
    """Load by path, matching the convention in the sibling test modules --
    scripts/eval is not an installed package, so a plain `import env` fails
    under pytest."""
    module_path = Path(__file__).resolve().parents[1] / "env.py"
    spec = importlib.util.spec_from_file_location("eval_env_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["eval_env_for_tests"] = module
    spec.loader.exec_module(module)
    return module


_env = _load_env_module()
describe_credential = _env.describe_credential
load_backend_env = _env.load_backend_env


@pytest.fixture
def env_file(tmp_path):
    path = tmp_path / ".env"
    path.write_text(
        "OPENALEX_API_KEY=file-value\n"
        "SOME_OTHER_KEY=other\n"
        "# a comment\n"
        "\n"
        'QUOTED="quoted-value"\n'
    )
    return path


class TestLoading:
    def test_sets_variables_from_file(self, env_file, monkeypatch):
        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        monkeypatch.delenv("SOME_OTHER_KEY", raising=False)

        applied = load_backend_env(env_file)

        assert os.environ["OPENALEX_API_KEY"] == "file-value"
        assert os.environ["SOME_OTHER_KEY"] == "other"
        assert set(applied) >= {"OPENALEX_API_KEY", "SOME_OTHER_KEY"}

    def test_strips_quotes(self, env_file, monkeypatch):
        monkeypatch.delenv("QUOTED", raising=False)
        load_backend_env(env_file)
        assert os.environ["QUOTED"] == "quoted-value"

    def test_an_exported_value_wins(self, env_file, monkeypatch):
        """The important one. A shell export or a test harness must beat a file on
        disk, or `NOESIS_LLM_KILL_SWITCH=1 python3 ...` could be silently undone by
        whatever happens to sit in .env."""
        monkeypatch.setenv("OPENALEX_API_KEY", "exported-value")

        applied = load_backend_env(env_file)

        assert os.environ["OPENALEX_API_KEY"] == "exported-value"
        assert "OPENALEX_API_KEY" not in applied

    def test_override_true_lets_the_file_win(self, env_file, monkeypatch):
        monkeypatch.setenv("OPENALEX_API_KEY", "exported-value")
        load_backend_env(env_file, override=True)
        assert os.environ["OPENALEX_API_KEY"] == "file-value"

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert load_backend_env(tmp_path / "nope.env") == []

    def test_returns_names_never_values(self, env_file, monkeypatch):
        """Callers log this. It must be impossible to leak a credential through it."""
        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        applied = load_backend_env(env_file)
        assert "file-value" not in " ".join(applied)


class TestDescribeCredential:
    def test_reports_set_without_the_value(self, monkeypatch):
        monkeypatch.setenv("SECRET_THING", "hunter2")
        described = describe_credential("SECRET_THING")
        assert described == "SECRET_THING=set"
        assert "hunter2" not in described

    def test_reports_unset(self, monkeypatch):
        monkeypatch.delenv("SECRET_THING", raising=False)
        assert describe_credential("SECRET_THING") == "SECRET_THING=unset"

    def test_empty_string_counts_as_unset(self, monkeypatch):
        monkeypatch.setenv("SECRET_THING", "")
        assert describe_credential("SECRET_THING") == "SECRET_THING=unset"
