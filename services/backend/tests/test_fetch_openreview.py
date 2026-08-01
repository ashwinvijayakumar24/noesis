import importlib.util
import sys
from pathlib import Path

import pytest


def _load_fetch_module():
    repo_root = Path(__file__).resolve().parents[3]
    module_path = repo_root / "scripts" / "eval" / "fetch_openreview.py"
    spec = importlib.util.spec_from_file_location("fetch_openreview_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["fetch_openreview_for_tests"] = module
    spec.loader.exec_module(module)
    return module


fetch_openreview = _load_fetch_module()


def test_classify_reply_handles_v2_invitation_lists():
    assert fetch_openreview._classify_reply(
        {"invitations": ["ICLR.cc/2024/Conference/Submission1/-/Official_Review"]}
    ) == "review"
    assert fetch_openreview._classify_reply(
        {"invitations": ["ICLR.cc/2024/Conference/Submission1/-/Meta_Review"]}
    ) == "meta"
    assert fetch_openreview._classify_reply(
        {"invitations": ["ICLR.cc/2024/Conference/Submission1/-/Decision"]}
    ) == "decision"
    assert fetch_openreview._classify_reply(
        {"invitations": ["ICLR.cc/2024/Conference/Submission1/-/Author_Rebuttal"]}
    ) == "other"


def test_extract_review_fields_unwraps_content_values_and_numeric_prefixes():
    reply = {
        "content": {
            "summary": {"value": "Clear summary"},
            "strengths": {"value": "Strong experiments"},
            "weaknesses": {"value": "Missing ablations"},
            "questions": {"value": "Why this baseline?"},
            "rating": {"value": "6: marginally above acceptance threshold"},
            "confidence": {"value": "4: You are confident in your assessment"},
            "soundness": {"value": "3: good"},
            "presentation": {"value": "2: fair"},
            "contribution": {"value": "3: good"},
        }
    }

    fields = fetch_openreview._extract_review_fields(reply)

    assert fields == {
        "rating": 6,
        "confidence": 4,
        "soundness": 3,
        "presentation": 2,
        "contribution": 3,
        "summary": "Clear summary",
        "strengths": "Strong experiments",
        "weaknesses": "Missing ablations",
        "questions": "Why this baseline?",
    }


def test_extract_review_fields_falls_back_to_legacy_review_body():
    fields = fetch_openreview._extract_review_fields({"content": {"review": {"value": "One bundled review"}}})

    assert fields["weaknesses"] == "One bundled review"


@pytest.mark.parametrize(
    ("decision", "accepted"),
    [
        ("Accept (poster)", True),
        ("Reject", False),
        ("Desk Reject", False),
        ("Invite to Workshop Track", False),
    ],
)
def test_is_accepted(decision, accepted):
    assert fetch_openreview._is_accepted(decision) is accepted


def test_validate_gold_fails_loudly_for_missing_required_data(tmp_path):
    gold = {
        "paper_id": "paper1",
        "reviews": [
            {"weaknesses": "a"},
            {"weaknesses": "b"},
            {"weaknesses": "c"},
        ],
        "decision": "",
    }
    pdf = tmp_path / "paper1.pdf"
    pdf.write_bytes(b"%PDF-1.7")

    with pytest.raises(RuntimeError, match="no decision"):
        fetch_openreview._validate_gold(gold, pdf)


def test_fetch_venue_skips_bad_submissions_until_limit(tmp_path, monkeypatch):
    class Client:
        def get_notes(self, invitation, limit):
            assert limit >= 6
            return [{"id": "bad"}, {"id": "good1"}, {"id": "good2"}]

    monkeypatch.setattr(fetch_openreview, "_client", lambda: Client())
    monkeypatch.setattr(fetch_openreview, "_resolve_submission_invitation", lambda client, venue_id: "venue/-/Submission")

    def build_gold(client, venue_id, submission, out_dir):
        if submission["id"] == "bad":
            raise RuntimeError("PDF download failed")
        path = out_dir / "venue" / f"{submission['id']}.json"
        return (
            {
                "paper_id": submission["id"],
                "reviews": [{"weaknesses": "a"}, {"weaknesses": "b"}, {"weaknesses": "c"}],
                "decision": "Reject",
                "raw_reply_invitations": [],
            },
            path,
        )

    monkeypatch.setattr(fetch_openreview, "_build_gold", build_gold)

    paths = fetch_openreview.fetch_venue("venue", limit=2, out_dir=tmp_path, delay=0)

    assert [path.name for path in paths] == ["good1.json", "good2.json"]
