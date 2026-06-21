"""
Fetch public OpenReview submissions and peer reviews into Noesis eval gold JSON.

Phase 0 only: prove anonymous ICLR pulls work, normalize the review schema, and
fail loudly when the venue shape does not match the eval assumptions.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin

import requests

API_BASEURL = "https://api2.openreview.net"
WEB_BASEURL = "https://openreview.net"
EVAL_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = EVAL_DIR / "openreview"

ReplyKind = Literal["review", "meta", "decision", "other"]


def _client():
    try:
        import openreview  # type: ignore[import]
    except ImportError as exc:
        raise RuntimeError(
            "openreview-py is required. Install backend requirements or run "
            "`pip install openreview-py` in the eval environment."
        ) from exc

    return openreview.api.OpenReviewClient(baseurl=API_BASEURL)


def _note_to_dict(note: Any) -> dict:
    if isinstance(note, dict):
        return note
    if hasattr(note, "to_json"):
        return note.to_json()
    return {
        key: getattr(note, key)
        for key in ("id", "forum", "number", "content", "details", "invitations", "invitation", "signatures")
        if hasattr(note, key)
    }


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"value"}:
        return value["value"]
    if isinstance(value, dict) and "value" in value and len(value) <= 3:
        return value["value"]
    return value


def _content_value(content: dict, key: str, default: Any = "") -> Any:
    return _unwrap(content.get(key, default))


def _venue_slug(venue_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", venue_id).strip("_")
    return slug or "venue"


def _paper_slug(paper_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", paper_id).strip("_")


def _invitation_ids(reply: dict) -> list[str]:
    invitations = reply.get("invitations")
    if isinstance(invitations, list):
        values = [str(inv) for inv in invitations]
    elif invitations:
        values = [str(invitations)]
    else:
        values = []
    invitation = reply.get("invitation")
    if invitation:
        values.append(str(invitation))
    return values


def _classify_reply(reply: dict) -> ReplyKind:
    invitation_ids = _invitation_ids(reply)
    suffixes = [inv.rsplit("/-/", 1)[-1] for inv in invitation_ids]

    if any(s == "Official_Review" for s in suffixes):
        return "review"
    if any(s in {"Meta_Review", "Meta_Review_Revision"} for s in suffixes):
        return "meta"
    if any(s in {"Decision", "Acceptance_Decision", "Final_Decision"} for s in suffixes):
        return "decision"
    return "other"


def _parse_numeric(value: Any) -> int | float | str | None:
    value = _unwrap(value)
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    match = re.match(r"^-?\d+(?:\.\d+)?", text)
    if not match:
        return text
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def _extract_review_fields(reply: dict) -> dict:
    content = reply.get("content") or {}
    fields = {
        "rating": _parse_numeric(content.get("rating")),
        "confidence": _parse_numeric(content.get("confidence")),
        "soundness": _parse_numeric(content.get("soundness")),
        "presentation": _parse_numeric(content.get("presentation")),
        "contribution": _parse_numeric(content.get("contribution")),
        "summary": str(_content_value(content, "summary", "") or ""),
        "strengths": str(_content_value(content, "strengths", "") or ""),
        "weaknesses": str(_content_value(content, "weaknesses", "") or ""),
        "questions": str(_content_value(content, "questions", "") or ""),
    }

    # Older venues may bundle review text instead of separating weaknesses.
    if not fields["weaknesses"] and content.get("review"):
        fields["weaknesses"] = str(_content_value(content, "review", "") or "")

    return fields


def _extract_meta_review(reply: dict | None) -> dict:
    if not reply:
        return {}
    content = reply.get("content") or {}
    return {
        "recommendation": str(
            _content_value(content, "recommendation", _content_value(content, "decision", "")) or ""
        ),
        "primary_reasons": str(
            _content_value(
                content,
                "primary_reasons",
                _content_value(content, "metareview", _content_value(content, "summary", "")),
            )
            or ""
        ),
    }


def _extract_decision(reply: dict | None) -> str:
    if not reply:
        return ""
    content = reply.get("content") or {}
    for key in ("decision", "recommendation", "title"):
        value = _content_value(content, key, "")
        if value:
            return str(value)
    return ""


def _is_accepted(decision: str) -> bool:
    lowered = decision.lower()
    return "accept" in lowered and "reject" not in lowered


def _resolve_submission_invitation(client: Any, venue_id: str) -> str:
    group = _note_to_dict(client.get_group(venue_id))
    content = group.get("content") or {}
    submission_name = _content_value(content, "submission_name", "")
    if not submission_name:
        raise RuntimeError(f"Venue group {venue_id!r} does not expose content.submission_name")
    return f"{venue_id}/-/{submission_name}"


def _reply_notes(client: Any, submission: dict) -> list[dict]:
    details = submission.get("details") or {}
    replies = details.get("replies") or []
    if replies:
        return [_note_to_dict(reply) for reply in replies]

    forum = submission.get("forum") or submission.get("id")
    if not forum:
        return []
    return [_note_to_dict(note) for note in client.get_all_notes(forum=forum)]


def _pdf_url(submission: dict) -> str:
    content = submission.get("content") or {}
    pdf = _content_value(content, "pdf", "")
    if not pdf:
        return ""
    if str(pdf).startswith("http"):
        return str(pdf)
    return urljoin(WEB_BASEURL, str(pdf))


def _download_pdf(client: Any, submission: dict, pdf_path: Path) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_url = _pdf_url(submission)

    if pdf_url:
        response = requests.get(pdf_url, timeout=30)
        if response.ok and response.content.startswith(b"%PDF"):
            pdf_path.write_bytes(response.content)
            return

    paper_id = submission.get("id")
    if not paper_id:
        raise RuntimeError("Submission missing id; cannot download PDF")
    pdf_bytes = client.get_pdf(paper_id)
    if not isinstance(pdf_bytes, bytes) or not pdf_bytes.startswith(b"%PDF"):
        raise RuntimeError(f"PDF download failed for {paper_id}")
    pdf_path.write_bytes(pdf_bytes)


def _validate_gold(gold: dict, pdf_abs_path: Path) -> None:
    if len(gold["reviews"]) < 3:
        raise RuntimeError(f"{gold['paper_id']}: expected at least 3 official reviews")
    if not any((review.get("weaknesses") or "").strip() for review in gold["reviews"]):
        raise RuntimeError(f"{gold['paper_id']}: no non-empty weaknesses found")
    if not gold.get("decision"):
        raise RuntimeError(f"{gold['paper_id']}: no decision reply found")
    if not pdf_abs_path.exists() or pdf_abs_path.stat().st_size == 0:
        raise RuntimeError(f"{gold['paper_id']}: PDF was not downloaded")


def _build_gold(client: Any, venue_id: str, submission: dict, out_dir: Path) -> tuple[dict, Path]:
    paper_id = str(submission["id"])
    venue_slug = _venue_slug(venue_id)
    paper_slug = _paper_slug(paper_id)
    paper_dir = out_dir / venue_slug
    pdf_abs_path = paper_dir / f"{paper_slug}.pdf"
    json_abs_path = paper_dir / f"{paper_slug}.json"

    replies = _reply_notes(client, submission)
    raw_reply_invitations = sorted({inv for reply in replies for inv in _invitation_ids(reply)})
    classified: dict[ReplyKind, list[dict]] = {"review": [], "meta": [], "decision": [], "other": []}
    for reply in replies:
        classified[_classify_reply(reply)].append(reply)

    reviews = []
    for idx, reply in enumerate(classified["review"], start=1):
        reviews.append({"reviewer": f"anon{idx}", **_extract_review_fields(reply)})

    decision = _extract_decision(classified["decision"][0] if classified["decision"] else None)
    content = submission.get("content") or {}
    _download_pdf(client, submission, pdf_abs_path)
    rel_pdf_path = pdf_abs_path.relative_to(EVAL_DIR).as_posix()

    gold = {
        "paper_id": paper_id,
        "venue": venue_id,
        "title": str(_content_value(content, "title", "") or ""),
        "pdf_path": rel_pdf_path,
        "pdf_url": _pdf_url(submission),
        "abstract": str(_content_value(content, "abstract", "") or ""),
        "decision": decision,
        "accepted": _is_accepted(decision),
        "reviews": reviews,
        "meta_review": _extract_meta_review(classified["meta"][0] if classified["meta"] else None),
        "raw_reply_invitations": raw_reply_invitations,
    }
    _validate_gold(gold, pdf_abs_path)
    return gold, json_abs_path


def fetch_venue(venue_id: str, limit: int = 20, out_dir: Path = DEFAULT_OUT_DIR, delay: float = 1.0) -> list[Path]:
    client = _client()
    submission_invitation = _resolve_submission_invitation(client, venue_id)
    print(f"[openreview] venue={venue_id}")
    print(f"[openreview] submission_invitation={submission_invitation}")

    # openreview-py 1.54.0 currently raises KeyError("count") for this venue
    # when `details="replies"` is combined with `get_all_notes`. Fetch replies
    # by forum instead; this still enumerates exact reply invitations live.
    candidate_limit = max(limit * 3, limit + 10)
    submissions = client.get_notes(invitation=submission_invitation, limit=candidate_limit)
    if not submissions:
        raise RuntimeError(f"No submissions found for invitation {submission_invitation}")

    written: list[Path] = []
    skipped: list[str] = []
    for raw_submission in submissions:
        if len(written) >= limit:
            break
        submission = _note_to_dict(raw_submission)
        paper_id = str(submission.get("id") or "<unknown>")
        try:
            gold, json_path = _build_gold(client, venue_id, submission, out_dir)
        except Exception as exc:
            skipped.append(paper_id)
            print(f"[openreview] skipped {paper_id}: {exc}")
            continue
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(gold, indent=2, sort_keys=True) + "\n")
        written.append(json_path)
        print(
            f"[openreview] wrote {json_path} reviews={len(gold['reviews'])} "
            f"decision={gold['decision']!r}"
        )
        print(f"[openreview] raw_reply_invitations={gold['raw_reply_invitations']}")
        if delay and len(written) < limit:
            time.sleep(delay)

    if len(written) < limit:
        raise RuntimeError(
            f"Only wrote {len(written)} valid OpenReview gold files for {venue_id}; "
            f"requested {limit}, skipped={skipped}"
        )

    return written


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch OpenReview papers and reviews into eval gold JSON.")
    parser.add_argument("--venue", default="ICLR.cc/2024/Conference")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    paths = fetch_venue(args.venue, args.limit, args.out_dir, args.delay)
    print(f"[openreview] complete: wrote {len(paths)} gold files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
