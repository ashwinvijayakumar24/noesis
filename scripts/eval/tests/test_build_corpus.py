"""Unit tests for scripts/eval/build_corpus.py — the references.json sidecar.

The sidecar is the resolution *denominator*: without it
scripts/eval/retrieval/labels.py cannot tell "40 of 40 references resolved" from
"40 of 544", and correctly refuses to report a rate. These tests pin the schema
against the real consumer.

No network: the OpenAlex client and the PDF downloader are both mocked. Nothing
here makes an LLM call.
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, EVAL_DIR / relpath)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


bc = _load("build_corpus_for_tests", "build_corpus.py")
labels = _load("retrieval_labels_for_tests", "retrieval/labels.py")


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _work(oa_id, title, doi=None, oa_url=None, year=2020, author="Ada Lovelace"):
    return {
        "id": f"https://openalex.org/{oa_id}",
        "display_name": title,
        "doi": f"https://doi.org/{doi}" if doi else None,
        "publication_year": year,
        "authorships": [{"author": {"display_name": author}}],
        "open_access": {"oa_url": oa_url},
        "primary_location": {},
    }


class FakeOpenAlex:
    """Stands in for _resolve_ref. Keyed by reference title."""

    def __init__(self, by_title):
        self.by_title = by_title
        self.calls = []

    async def __call__(self, session, ref):
        self.calls.append(ref.get("title"))
        return ref, self.by_title.get(ref.get("title"))


class FakeDownloader:
    """Stands in for _download_pdf. ``fails`` holds urls that 404."""

    def __init__(self, fails=()):
        self.fails = set(fails)
        self.calls = []

    async def __call__(self, session, url, dest):
        self.calls.append(url)
        if url in self.fails:
            return False
        # Distinct bytes per URL. Document ids downstream are content-addressed
        # (uuid5 over the file's sha256), so identical bytes collapse to ONE
        # document -- the same dedup that turned 39 real corpus files into 38.
        # Writing the same payload for every reference made two resolved refs
        # look like one document, which read as a matcher bug rather than the
        # fixture bug it was.
        dest.write_bytes(b"%PDF-1.4\n" + url.encode() + b"\n" + b"x" * 6000)
        return True


@pytest.fixture
def patched(monkeypatch, tmp_path):
    """Redirect CORPORA_DIR to tmp_path and neutralise all network calls."""
    monkeypatch.setattr(bc, "CORPORA_DIR", tmp_path / "corpora")

    class _NoSession:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(bc.aiohttp, "ClientSession", lambda *a, **k: _NoSession())
    return tmp_path


@pytest.fixture
def source_pdf(tmp_path):
    path = tmp_path / "source.pdf"
    path.write_bytes(b"%PDF-1.4 fake manuscript")
    return path


def _run(corpus, source, refs, **kw):
    return asyncio.run(bc.build_corpus_from_refs(corpus, source, refs, **kw))


def _sidecar(tmp_path, corpus="c1"):
    return json.loads((tmp_path / "corpora" / corpus / bc.REFERENCES_SIDECAR).read_text())


# ---------------------------------------------------------------------------
# Sidecar completeness
# ---------------------------------------------------------------------------


def test_sidecar_has_one_entry_per_reference_including_unresolved(
    patched, source_pdf, monkeypatch
):
    refs = [
        {"title": "Resolvable paper", "doi": "10.1/a", "raw": "A. Author. Resolvable paper. 2020."},
        {"title": "Unknown paper", "doi": None, "raw": "B. Author. Unknown paper. 2021."},
        {"title": "Paywalled paper", "doi": "10.1/c", "raw": "C. Author. Paywalled paper. 2019."},
    ]
    resolver = FakeOpenAlex({
        "Resolvable paper": _work("W1", "Resolvable paper", "10.1/a", "http://x/a.pdf"),
        "Paywalled paper": _work("W3", "Paywalled paper", "10.1/c", oa_url=None),
    })
    monkeypatch.setattr(bc, "_resolve_ref", resolver)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    downloaded, entries = _run("c1", source_pdf, refs, max_papers=0)

    assert downloaded == 1
    assert len(entries) == len(refs)
    payload = _sidecar(patched)
    assert payload["references_attempted"] == 3
    assert payload["references_resolved"] == 1
    assert len(payload["references"]) == 3


def test_every_distinguished_outcome_appears(patched, source_pdf, monkeypatch):
    refs = [
        {"title": "Downloads fine", "doi": None, "raw": "r1"},
        {"title": "Not in openalex", "doi": None, "raw": "r2"},
        {"title": "No oa pdf", "doi": None, "raw": "r3"},
        {"title": "Download breaks", "doi": None, "raw": "r4"},
        {"title": "Beyond the cap", "doi": None, "raw": "r5"},
    ]
    resolver = FakeOpenAlex({
        "Downloads fine": _work("W1", "Downloads fine", oa_url="http://x/ok.pdf"),
        "No oa pdf": _work("W3", "No oa pdf", oa_url=None),
        "Download breaks": _work("W4", "Download breaks", oa_url="http://x/bad.pdf"),
        "Beyond the cap": _work("W5", "Beyond the cap", oa_url="http://x/cap.pdf"),
    })
    monkeypatch.setattr(bc, "_resolve_ref", resolver)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader(fails={"http://x/bad.pdf"}))

    _run("c1", source_pdf, refs, max_papers=4)

    by_status = {e["raw"]: e["status"] for e in _sidecar(patched)["references"]}
    assert by_status == {
        "r1": bc.STATUS_RESOLVED,
        "r2": bc.STATUS_NO_OPENALEX,
        "r3": bc.STATUS_NO_OA_PDF,
        "r4": bc.STATUS_DOWNLOAD_FAILED,
        "r5": bc.STATUS_SKIPPED,
    }
    # The truncated reference was never sent to OpenAlex.
    assert "Beyond the cap" not in resolver.calls
    # …but it still counts toward the denominator.
    assert len(_sidecar(patched)["references"]) == 5


def test_resolved_entry_records_openalex_id_doi_and_filename(
    patched, source_pdf, monkeypatch
):
    refs = [{"title": "Attention is all you need", "doi": None, "raw": "r1"}]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Attention is all you need": _work(
            "W42", "Attention is all you need", "10.5555/attn", "http://x/attn.pdf",
            year=2017, author="Ashish Vaswani",
        )
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    entry = _sidecar(patched)["references"][0]
    assert entry["openalex_id"] == "https://openalex.org/W42"
    assert entry["doi"] == "10.5555/attn"       # bare doi, not a url
    assert entry["title"] == "Attention is all you need"
    assert entry["filename"] == "vaswani_2017_attention_is_all_you_need.pdf"
    assert (patched / "corpora" / "c1" / entry["filename"]).exists()


# ---------------------------------------------------------------------------
# The test that matters: labels.py consumes what we write
# ---------------------------------------------------------------------------


def test_labels_py_reads_the_sidecar_and_recovers_the_denominator(
    patched, source_pdf, monkeypatch
):
    refs = [
        {"title": "Resolved one", "doi": None, "raw": "r1"},
        {"title": "Resolved two", "doi": None, "raw": "r2"},
        {"title": "Missing three", "doi": None, "raw": "r3"},
        {"title": "Missing four", "doi": None, "raw": "r4"},
    ]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Resolved one": _work("W1", "Resolved one", oa_url="http://x/1.pdf", author="Alice Alpha"),
        "Resolved two": _work("W2", "Resolved two", oa_url="http://x/2.pdf", author="Bob Beta"),
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    label_set = labels.build_label_set(patched / "corpora")
    topic = label_set.topics["c1"]

    assert topic.denominator_recoverable is True
    assert topic.references_total == 4          # not 2 — unresolved refs counted
    assert len(topic.relevant_doc_ids) == 2
    assert topic.resolution_rate == pytest.approx(0.5)
    assert sorted(u.title for u in topic.unresolved) == ["Missing four", "Missing three"]

    report = label_set.resolution_report()
    assert report["references_attempted"] == 4
    assert report["resolution_rate"] == pytest.approx(0.5)
    assert report["denominator_recoverable"] is True


def test_labels_py_reports_unknown_without_a_sidecar(patched, source_pdf, monkeypatch):
    """Control: the failure mode the sidecar exists to fix."""
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Resolved one": _work("W1", "Resolved one", oa_url="http://x/1.pdf", author="Alice Alpha"),
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())
    _run("c1", source_pdf, [{"title": "Resolved one", "doi": None, "raw": "r1"}], max_papers=0)

    (patched / "corpora" / "c1" / bc.REFERENCES_SIDECAR).unlink()

    label_set = labels.build_label_set(patched / "corpora")
    assert label_set.topics["c1"].denominator_recoverable is False
    assert label_set.topics["c1"].resolution_rate is None
    assert label_set.resolution_report()["references_attempted"] is None


# ---------------------------------------------------------------------------
# Resumability
# ---------------------------------------------------------------------------


def test_second_run_redownloads_nothing_and_does_not_duplicate_entries(
    patched, source_pdf, monkeypatch
):
    refs = [
        {"title": "Resolved one", "doi": None, "raw": "r1"},
        {"title": "Missing two", "doi": None, "raw": "r2"},
    ]
    resolver = FakeOpenAlex({
        "Resolved one": _work("W1", "Resolved one", oa_url="http://x/1.pdf"),
    })
    downloader = FakeDownloader()
    monkeypatch.setattr(bc, "_resolve_ref", resolver)
    monkeypatch.setattr(bc, "_download_pdf", downloader)

    first_count, first_entries = _run("c1", source_pdf, refs, max_papers=0)
    first_payload = _sidecar(patched)

    second_count, second_entries = _run("c1", source_pdf, refs, max_papers=0)
    second_payload = _sidecar(patched)

    assert (second_count, len(second_entries)) == (first_count, len(first_entries)) == (1, 2)
    assert len(second_payload["references"]) == 2
    assert len(resolver.calls) == 2      # only the first run queried OpenAlex
    assert len(downloader.calls) == 1    # and only the first run downloaded
    assert {e["raw"]: e["status"] for e in second_payload["references"]} == \
           {e["raw"]: e["status"] for e in first_payload["references"]}


def test_changed_source_pdf_invalidates_the_resume_index(patched, source_pdf, monkeypatch):
    refs = [{"title": "Resolved one", "doi": None, "raw": "r1"}]
    resolver = FakeOpenAlex({"Resolved one": _work("W1", "Resolved one", oa_url="http://x/1.pdf")})
    monkeypatch.setattr(bc, "_resolve_ref", resolver)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)
    source_pdf.write_bytes(b"%PDF-1.4 a different manuscript")
    _run("c1", source_pdf, refs, max_papers=0)

    assert len(resolver.calls) == 2
    assert len(_sidecar(patched)["references"]) == 1


def test_budget_exhaustion_marks_pending_not_missing(patched, source_pdf, monkeypatch):
    """A ref that was never looked up must not be recorded as 'not in OpenAlex'.

    That mislabelling is permanent: the resume index would skip it forever and
    the corpus would be quietly, irreversibly short.
    """
    refs = [
        {"title": "Looked up fine", "doi": None, "raw": "r1"},
        {"title": "Never looked up", "doi": None, "raw": "r2"},
    ]

    async def _budget(session, ref):
        if ref["title"] == "Never looked up":
            raise bc.OpenAlexBudgetExhausted("daily budget spent")
        return ref, _work("W1", "Looked up fine", oa_url="http://x/1.pdf")

    monkeypatch.setattr(bc, "_resolve_ref", _budget)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    with pytest.raises(bc.OpenAlexBudgetExhausted):
        _run("c1", source_pdf, refs, max_papers=0)

    by_status = {e["raw"]: e["status"] for e in _sidecar(patched)["references"]}
    assert by_status == {"r1": bc.STATUS_RESOLVED, "r2": bc.STATUS_PENDING}

    # …and the pending one is retried on the next run.
    calls = []

    async def _ok(session, ref):
        calls.append(ref["title"])
        return ref, _work("W2", "Never looked up", oa_url="http://x/2.pdf")

    monkeypatch.setattr(bc, "_resolve_ref", _ok)
    _run("c1", source_pdf, refs, max_papers=0)
    assert calls == ["Never looked up"]
    assert {e["status"] for e in _sidecar(patched)["references"]} == {bc.STATUS_RESOLVED}


# ---------------------------------------------------------------------------
# Degenerate inputs
# ---------------------------------------------------------------------------


def test_reference_without_a_doi_is_resolved_by_title(patched, source_pdf, monkeypatch):
    refs = [{"title": "No doi anywhere", "doi": None, "raw": "r1"}]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "No doi anywhere": _work("W1", "No doi anywhere", doi=None, oa_url="http://x/1.pdf")
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    entry = _sidecar(patched)["references"][0]
    assert entry["doi"] is None
    assert entry["status"] == bc.STATUS_RESOLVED


def test_download_404_is_recorded_not_raised(patched, source_pdf, monkeypatch):
    refs = [{"title": "Gone", "doi": None, "raw": "r1"}]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Gone": _work("W1", "Gone", oa_url="http://x/404.pdf")
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader(fails={"http://x/404.pdf"}))

    downloaded, entries = _run("c1", source_pdf, refs, max_papers=0)

    assert downloaded == 0
    assert entries[0]["status"] == bc.STATUS_DOWNLOAD_FAILED
    assert entries[0]["filename"] is None
    assert not list((patched / "corpora" / "c1").glob("*.pdf"))


def test_empty_reference_list_writes_an_empty_sidecar(patched, source_pdf, monkeypatch):
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({}))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    downloaded, entries = _run("c1", source_pdf, [], max_papers=0)

    assert (downloaded, entries) == (0, [])
    assert _sidecar(patched)["references"] == []
    # labels.py must treat "0 attempted" as recoverable-but-empty, not unknown.
    label_set = labels.build_label_set(patched / "corpora")
    assert label_set.topics["c1"].references_total == 0
    assert label_set.topics["c1"].resolution_rate is None


def test_malformed_openalex_response_does_not_crash(patched, source_pdf, monkeypatch):
    refs = [
        {"title": "Junk one", "doi": None, "raw": "r1"},
        {"title": "Junk two", "doi": None, "raw": "r2"},
        {"title": "Junk three", "doi": None, "raw": "r3"},
    ]

    async def _flaky(session, ref):
        if ref["title"] == "Junk one":
            raise RuntimeError("connection reset")
        if ref["title"] == "Junk two":
            return ref, {}                      # no id, no display_name, no oa
        return ref, {"id": None, "open_access": None, "primary_location": None}

    monkeypatch.setattr(bc, "_resolve_ref", _flaky)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    downloaded, entries = _run("c1", source_pdf, refs, max_papers=0)

    assert downloaded == 0
    assert len(entries) == 3
    assert {e["status"] for e in entries} <= {bc.STATUS_NO_OPENALEX, bc.STATUS_NO_OA_PDF}
    labels.build_label_set(patched / "corpora")  # still parseable


def test_corrupt_sidecar_is_ignored_rather_than_fatal(patched, source_pdf, monkeypatch):
    corpus_dir = patched / "corpora" / "c1"
    corpus_dir.mkdir(parents=True)
    (corpus_dir / bc.REFERENCES_SIDECAR).write_text("{not json")

    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({}))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())
    _, entries = _run("c1", source_pdf, [{"title": "x y z", "doi": None, "raw": "r1"}], max_papers=0)

    assert len(entries) == 1


# ---------------------------------------------------------------------------
# PDF reference parsing (pure, offline)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "entry,expected",
    [
        (
            "T. Akiba, S. Sano, T. Yanase, T. Ohta, and M. Koyama. Optuna: A next-generation "
            "hyperparameter optimization framework. In KDD, 2019.",
            "Optuna: A next-generation hyperparameter optimization framework",
        ),
        (
            "J. L. Ba, J. R. Kiros, and G. E. Hinton. Layer normalization. arXiv, 1607.06450v1, 2016.",
            "Layer normalization",
        ),
        (
            'Xie, Jin, and Liang Gao. "Review on flexible job shop scheduling." IET CIM 1, 2018.',
            "Review on flexible job shop scheduling",
        ),
    ],
)
def test_guess_title(entry, expected):
    assert bc._guess_title(entry) == expected


def test_split_entries_keeps_long_author_lists_together():
    bibliography = "\n".join([
        "S. Borgeaud, A. Mensch, J. Hoffmann, T. Cai, E. Rutherford,",
        "K. Millican, G. van den Driessche, J. Lespiau, and L. Sifre.",
        "Improving language models by retrieving from trillions of tokens.",
        "In ICML, 2022.",
        "L. Bottou and V. Vapnik. Local learning algorithms. Neural Computation, 4, 1992.",
    ])
    entries = bc._split_entries(bibliography)
    assert len(entries) == 2
    assert entries[0].startswith("S. Borgeaud")
    assert "trillions of tokens" in entries[0]
    assert entries[1].startswith("L. Bottou")


def test_extract_refs_picks_up_doi_and_arxiv_ids(tmp_path, monkeypatch):
    bibliography = (
        "A. Author and B. Author. A paper with a doi. Journal, 2020. doi: 10.1234/abcd.\n"
        "C. Author. A paper on the preprint server. arXiv preprint arXiv:2101.12345, 2021.\n"
        "D. Author. A paper with no identifier at all. In NeurIPS, 2019.\n"
    )
    monkeypatch.setattr(bc, "_bibliography_text", lambda p: bibliography)
    refs = bc._extract_refs_from_pdf(tmp_path / "x.pdf")

    assert [r["doi"] for r in refs] == ["10.1234/abcd", "10.48550/arXiv.2101.12345", None]


def test_extract_refs_on_a_pdf_without_a_bibliography(tmp_path, monkeypatch):
    monkeypatch.setattr(bc, "_bibliography_text", lambda p: "")
    assert bc._extract_refs_from_pdf(tmp_path / "x.pdf") == []


# ---------------------------------------------------------------------------
# OpenAlex authentication
#
# OpenAlex authenticates with an ``api_key`` *query parameter* (confirmed at
# developers.openalex.org/api-reference/authentication, and live: a bogus key
# returns 401 "Invalid or missing API key"). Because the credential rides in
# the URL rather than a header, the interesting risk is not "does it work" but
# "where does it leak" — hence the redaction tests below.
# ---------------------------------------------------------------------------

SECRET = "oa-secret-key-do-not-log-9f3a2b"


@pytest.fixture
def with_key(monkeypatch):
    monkeypatch.setattr(bc, "_OA_API_KEY", SECRET)
    return SECRET


@pytest.fixture
def without_key(monkeypatch):
    monkeypatch.setattr(bc, "_OA_API_KEY", "")


class RecordingSession:
    """Captures the (url, params) of every request, and replays canned responses."""

    def __init__(self, responses=None):
        self.requests = []
        self._responses = list(responses or [])

    def get(self, url, params=None, **kw):
        self.requests.append((url, dict(params or {})))
        resp = self._responses.pop(0) if self._responses else FakeResponse(200, {})
        return resp

    async def close(self):
        pass


class FakeResponse:
    def __init__(self, status, headers, body=None):
        self.status = status
        self.headers = headers
        self._body = body if body is not None else {"id": "https://openalex.org/W1"}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self):
        return self._body


def test_api_key_is_sent_as_the_api_key_query_parameter(with_key):
    params = bc._polite({"search": "layer normalization"})
    assert params["api_key"] == SECRET
    # mailto is the polite pool, not authentication — both are sent.
    assert params["mailto"] == bc._OA_EMAIL


def test_without_a_key_requests_are_byte_for_byte_what_they_were(without_key):
    params = bc._polite({"search": "layer normalization"})
    assert "api_key" not in params
    assert set(params) == {"mailto", "select", "search"}


def test_budget_probe_carries_the_key_and_the_key_alone_authenticates(with_key):
    session = RecordingSession([FakeResponse(200, {"X-RateLimit-Remaining-USD": "0.94"})])
    budget = asyncio.run(bc.fetch_budget(session))

    url, params = session.requests[0]
    assert params["api_key"] == SECRET
    assert budget["remaining_usd"] == pytest.approx(0.94)


# ---------------------------------------------------------------------------
# The key must not escape into anything durable or printed
# ---------------------------------------------------------------------------


def test_key_never_appears_in_the_sidecar(patched, source_pdf, monkeypatch, with_key):
    refs = [{"title": "Resolved one", "doi": "10.1/a", "raw": "r1"},
            {"title": "Missing two", "doi": None, "raw": "r2"}]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Resolved one": _work("W1", "Resolved one", "10.1/a", "http://x/1.pdf"),
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    # Every byte the build wrote, not just the sidecar: downloaded PDFs are
    # named from OpenAlex metadata and could in principle carry request state.
    written = list((patched / "corpora").rglob("*"))
    assert written, "nothing was written — the test would pass vacuously"
    for path in written:
        if path.is_file():
            assert SECRET.encode() not in path.read_bytes(), f"key leaked into {path.name}"
            assert SECRET not in path.name


def test_key_never_appears_in_stdout(patched, source_pdf, monkeypatch, capsys, with_key):
    refs = [{"title": "Resolved one", "doi": "10.1/a", "raw": "r1"}]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({
        "Resolved one": _work("W1", "Resolved one", "10.1/a", "http://x/1.pdf"),
    }))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    captured = capsys.readouterr()
    assert SECRET not in captured.out + captured.err


def test_key_never_appears_in_a_raised_error(with_key, monkeypatch):
    """Construct the real failure path: a 429 that interpolates the key.

    The budget message echoes response headers verbatim, so a header carrying
    the request URL — which is where OpenAlex's credential lives — would put the
    key straight into the exception. Redaction has to be doing real work here,
    not merely happening to hold: the ``***`` assertion pins that.
    """
    monkeypatch.setattr(bc._throttle, "_delay", 0.0)
    session = RecordingSession([
        FakeResponse(429, {
            "Retry-After": "13907",
            "X-RateLimit-Remaining-USD": SECRET,
            "X-RateLimit-Prepaid-Remaining-USD": "0",
        })
    ])

    with pytest.raises(bc.OpenAlexBudgetExhausted) as exc:
        asyncio.run(bc._oa_get(session, "https://api.openalex.org/works", bc._polite()))

    assert SECRET not in str(exc.value)
    assert "***" in str(exc.value)          # it was there, and was scrubbed


def test_redact_is_a_noop_without_a_key(without_key):
    assert bc._redact("nothing to hide") == "nothing to hide"


def test_redact_scrubs_a_url_carrying_the_key(with_key):
    leaky = f"GET https://api.openalex.org/works?search=x&api_key={SECRET} failed"
    assert SECRET not in bc._redact(leaky)


def test_rejected_key_does_not_echo_the_key(with_key, monkeypatch):
    monkeypatch.setattr(bc._throttle, "_delay", 0.0)
    session = RecordingSession([FakeResponse(401, {})])
    with pytest.raises(bc.OpenAlexBudgetExhausted) as exc:
        asyncio.run(bc._oa_get(session, "https://api.openalex.org/works", bc._polite()))
    assert SECRET not in str(exc.value)
    assert "OPENALEX_API_KEY" in str(exc.value)


# ---------------------------------------------------------------------------
# --check-budget
# ---------------------------------------------------------------------------


def test_check_budget_parses_the_ratelimit_headers(monkeypatch, capsys, with_key):
    session = RecordingSession([FakeResponse(200, {
        "X-RateLimit-Limit-USD": "1.0",
        "X-RateLimit-Remaining-USD": "0.8734",
        "X-RateLimit-Prepaid-Remaining-USD": "1.0",
        "X-RateLimit-Reset": "10677",
    })])
    monkeypatch.setattr(bc, "_client_session", lambda: session)

    code = asyncio.run(bc.check_budget())
    out = capsys.readouterr().out

    assert code == 0
    assert "$0.8734" in out
    assert "prepaid balance: $1.0000" in out
    assert "spendable now: $1.8734" in out
    assert SECRET not in out


def test_check_budget_reports_unknown_when_headers_are_absent(monkeypatch, capsys, without_key):
    session = RecordingSession([FakeResponse(200, {})])
    monkeypatch.setattr(bc, "_client_session", lambda: session)

    code = asyncio.run(bc.check_budget())
    out = capsys.readouterr().out

    # Absent headers must read as "unknown", never as "$0.00 — do not start".
    assert "budget unknown" in out
    assert code == 0


def test_check_budget_reports_an_exhausted_budget(monkeypatch, capsys, without_key):
    """What the owner actually sees today, from the observed 429 headers."""
    session = RecordingSession([FakeResponse(429, {
        "Retry-After": "10677",
        "X-RateLimit-Limit-USD": "0.1",
        "X-RateLimit-Remaining-USD": "0",
        "X-RateLimit-Prepaid-Remaining-USD": "0",
        "X-RateLimit-Reset": "10677",
    })])
    monkeypatch.setattr(bc, "_client_session", lambda: session)

    code = asyncio.run(bc.check_budget())
    out = capsys.readouterr().out

    assert code == 2
    assert "spendable now: $0.0000" in out
    assert "resets in 3.0h" in out
    assert "openalex.org/pricing" in out


def test_check_budget_flags_a_rejected_key(monkeypatch, capsys, with_key):
    session = RecordingSession([FakeResponse(401, {})])
    monkeypatch.setattr(bc, "_client_session", lambda: session)

    code = asyncio.run(bc.check_budget())
    out = capsys.readouterr().out

    assert code == 1
    assert "API key rejected" in out
    assert SECRET not in out


def test_check_budget_is_one_request(monkeypatch, with_key):
    session = RecordingSession([FakeResponse(200, {"X-RateLimit-Remaining-USD": "1"})])
    monkeypatch.setattr(bc, "_client_session", lambda: session)
    asyncio.run(bc.check_budget())
    assert len(session.requests) == 1


# ---------------------------------------------------------------------------
# Pre-run estimate
# ---------------------------------------------------------------------------


def test_estimate_prices_title_searches_above_doi_lookups():
    """A DOI-less reference costs 10x, which is why the estimate reads them."""
    with_dois = [{"doi": "10.1/a"}] * 10
    without = [{"doi": None}] * 10
    _, cheap = bc._estimate_requests(10, with_dois)
    _, dear = bc._estimate_requests(10, without)
    assert dear > cheap


def test_underfunded_run_is_flagged_before_it_starts(monkeypatch, capsys):
    monkeypatch.setattr(bc, "_budget_at_start", {"remaining_usd": 0.002, "prepaid_usd": 0.0})
    bc._warn_if_underfunded(0.6)
    assert "spendable budget is $0.0020" in capsys.readouterr().out


def test_unknown_budget_does_not_warn(monkeypatch, capsys):
    monkeypatch.setattr(bc, "_budget_at_start", None)
    bc._warn_if_underfunded(0.6)
    assert capsys.readouterr().out == ""


def test_build_prints_the_request_estimate(patched, source_pdf, monkeypatch, capsys):
    refs = [{"title": f"Paper {i}", "doi": None, "raw": f"r{i}"} for i in range(10)]
    monkeypatch.setattr(bc, "_resolve_ref", FakeOpenAlex({}))
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    _run("c1", source_pdf, refs, max_papers=0)

    out = capsys.readouterr().out
    assert "~10 requests" in out
    assert "$0.010" in out


# ---------------------------------------------------------------------------
# 429 with a large Retry-After: still pending, never no_openalex_match
# ---------------------------------------------------------------------------


def test_large_retry_after_raises_and_records_pending(patched, source_pdf, monkeypatch):
    """The end-to-end version of the mislabelling guard, driven by a real 429.

    ``_oa_get`` is exercised for real here (not stubbed at ``_resolve_ref``), so
    this pins the whole path: 429 → OA_MAX_BACKOFF exceeded → raise → PENDING.
    """
    monkeypatch.setattr(bc._throttle, "_delay", 0.0)
    exhausted = FakeResponse(429, {
        "Retry-After": "13907",
        "X-RateLimit-Remaining-USD": "0",
        "X-RateLimit-Prepaid-Remaining-USD": "0",
    })

    async def _resolve(session, ref):
        # Same shape as the real _resolve_ref: it lets the 429 propagate.
        return await bc._oa_get(RecordingSession([exhausted]), bc._OA_BASE, bc._polite())

    monkeypatch.setattr(bc, "_resolve_ref", _resolve)
    monkeypatch.setattr(bc, "_download_pdf", FakeDownloader())

    refs = [{"title": "Never looked up", "doi": None, "raw": "r1"}]
    with pytest.raises(bc.OpenAlexBudgetExhausted):
        _run("c1", source_pdf, refs, max_papers=0)

    entry = _sidecar(patched)["references"][0]
    assert entry["status"] == bc.STATUS_PENDING
    assert entry["status"] != bc.STATUS_NO_OPENALEX
    # Pending refs stay in the denominator so the resolution rate stays honest.
    assert _sidecar(patched)["references_attempted"] == 1
