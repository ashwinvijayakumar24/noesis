"""Parser spike harness — Phase 1 of the GROBID-migration RFC.

Runs each available parser over a folder of PDFs and reports the metric that
actually matters for Noesis anchoring: the fraction of text-bearing structural
units that carry a usable page/bounding-box (so a revision task can be located
in the PDF). GROBID's weakness is sparse coordinates; layout parsers (Docling,
Marker) and even raw PyMuPDF give a bbox for every block.

Run inside the spike venv:
    .spike-venv/bin/python scripts/parser_spike.py pdfs/

Each parser is optional — if its import/service is unavailable it's skipped.
No dependency on the Noesis app; GROBID is called directly over HTTP.
"""

from __future__ import annotations

import sys
import time
import re
from pathlib import Path
from collections import Counter

GROBID_URL = "http://localhost:8070"
TEI_NS = {"tei": "http://www.tei-c.org/ns/1.0"}


def _metrics(blocks: list[dict], sections: list[str], seconds: float) -> dict:
    """blocks: [{'text': str, 'page': int|None, 'has_bbox': bool}]"""
    total = len(blocks)
    with_loc = sum(1 for b in blocks if b.get("has_bbox") or b.get("page") is not None)
    titles = [re.sub(r"\s+", " ", (t or "")).strip().lower() for t in sections if (t or "").strip()]
    dup_titles = len(titles) - len(set(titles))
    return {
        "blocks": total,
        "blocks_with_location": with_loc,
        "location_coverage": round(with_loc / total, 3) if total else 0.0,
        "sections": len(sections),
        "duplicate_headings": dup_titles,
        "seconds": round(seconds, 1),
    }


# ---------------- GROBID (baseline, via HTTP) ----------------

def run_grobid(pdf: bytes) -> dict | None:
    import requests
    import xml.etree.ElementTree as ET
    try:
        t0 = time.time()
        resp = requests.post(
            f"{GROBID_URL}/api/processFulltextDocument",
            files={"input": ("doc.pdf", pdf, "application/pdf")},
            data={"teiCoordinates": ["p", "s", "biblStruct", "figure", "table"]},
            timeout=180,
        )
        secs = time.time() - t0
        if resp.status_code != 200:
            return {"error": f"grobid http {resp.status_code}"}
        root = ET.fromstring(resp.text)
        body = root.find(".//tei:text/tei:body", TEI_NS)
        blocks, sections = [], []
        if body is not None:
            for div in body.findall(".//tei:div", TEI_NS):
                head = div.find("./tei:head", TEI_NS)
                if head is not None and (head.text or "").strip():
                    sections.append("".join(head.itertext()).strip())
                for p in div.findall("./tei:p", TEI_NS):
                    text = "".join(p.itertext()).strip()
                    if not text:
                        continue
                    has_coords = p.get("coords") is not None or any(
                        s.get("coords") for s in p.findall(".//tei:s", TEI_NS)
                    )
                    page = None
                    c = p.get("coords") or next((s.get("coords") for s in p.findall(".//tei:s", TEI_NS) if s.get("coords")), None)
                    if c:
                        try:
                            page = int(c.split(",")[0])
                        except Exception:
                            page = None
                    blocks.append({"text": text, "page": page, "has_bbox": has_coords})
        return _metrics(blocks, sections, secs)
    except Exception as e:
        return {"error": f"grobid: {type(e).__name__}: {e}"}


# ---------------- PyMuPDF (free coordinate-ceiling reference) ----------------

def run_pymupdf(pdf: bytes) -> dict | None:
    try:
        import fitz
        t0 = time.time()
        doc = fitz.open(stream=pdf, filetype="pdf")
        blocks = []
        for pno, page in enumerate(doc):
            for b in page.get_text("blocks") or []:
                text = (b[4] if len(b) > 4 else "").strip()
                if text:
                    blocks.append({"text": text, "page": pno + 1, "has_bbox": True})
        secs = time.time() - t0
        # PyMuPDF has no section structure — that's the point (full coords, no structure).
        return _metrics(blocks, [], secs)
    except Exception as e:
        return {"error": f"pymupdf: {type(e).__name__}: {e}"}


# ---------------- Docling (candidate) ----------------

def run_docling(path: Path) -> dict | None:
    try:
        from docling.document_converter import DocumentConverter
    except Exception as e:
        return {"error": f"docling not installed: {type(e).__name__}"}
    try:
        t0 = time.time()
        doc = DocumentConverter().convert(str(path)).document
        secs = time.time() - t0
        blocks, sections = [], []
        for item, _level in doc.iterate_items():
            text = getattr(item, "text", None)
            if not text or not str(text).strip():
                continue
            prov = getattr(item, "prov", None) or []
            has_bbox = bool(prov and getattr(prov[0], "bbox", None) is not None)
            page = getattr(prov[0], "page_no", None) if prov else None
            blocks.append({"text": str(text), "page": page, "has_bbox": has_bbox})
            label = str(getattr(item, "label", "") or "")
            if "header" in label.lower() or "title" in label.lower() or "section" in label.lower():
                sections.append(str(text))
        return _metrics(blocks, sections, secs)
    except Exception as e:
        return {"error": f"docling: {type(e).__name__}: {e}"}


# ---------------- Marker (candidate, optional) ----------------

def run_marker(path: Path) -> dict | None:
    try:
        from marker.converters.pdf import PdfConverter
        from marker.models import create_model_dict
    except Exception as e:
        return {"error": f"marker not installed: {type(e).__name__}"}
    try:
        t0 = time.time()
        conv = PdfConverter(artifact_dict=create_model_dict())
        rendered = conv(str(path))
        secs = time.time() - t0
        # Marker returns markdown + a blocks/JSON structure depending on version.
        blocks, sections = [], []
        meta = getattr(rendered, "metadata", {}) or {}
        page_blocks = meta.get("page_stats") or []
        # Fall back to markdown line count if structured blocks unavailable.
        md = getattr(rendered, "markdown", "") or ""
        for line in md.splitlines():
            if line.strip().startswith("#"):
                sections.append(line.lstrip("#").strip())
        # Marker block bboxes live in rendered.children/blocks across versions; treat
        # presence of page_stats as bbox-bearing (marker always carries bbox per block).
        approx_blocks = sum(int(p.get("text_extraction_method") is not None) for p in page_blocks) if page_blocks else len([l for l in md.splitlines() if l.strip()])
        for _ in range(approx_blocks):
            blocks.append({"text": "x", "page": 1, "has_bbox": True})
        return _metrics(blocks, sections, secs)
    except Exception as e:
        return {"error": f"marker: {type(e).__name__}: {e}"}


def main() -> None:
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "pdfs")
    pdfs = sorted(folder.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs in {folder}/")
        return
    parsers = [
        ("grobid", lambda p, b: run_grobid(b)),
        ("pymupdf", lambda p, b: run_pymupdf(b)),
        ("docling", lambda p, b: run_docling(p)),
        ("marker", lambda p, b: run_marker(p)),
    ]
    print(f"\n=== Parser spike over {len(pdfs)} PDF(s) ===\n")
    agg: dict[str, list[float]] = {}
    for pdf in pdfs:
        data = pdf.read_bytes()
        print(f"--- {pdf.name} ({len(data)//1024} KB) ---")
        for name, fn in parsers:
            r = fn(pdf, data)
            if r is None or "error" in r:
                print(f"  {name:8} : {(r or {}).get('error','skipped')}")
                continue
            print(
                f"  {name:8} : loc_coverage={r['location_coverage']:<5} "
                f"blocks={r['blocks']:<4} sections={r['sections']:<3} "
                f"dup_headings={r['duplicate_headings']:<2} {r['seconds']}s"
            )
            agg.setdefault(name, []).append(r["location_coverage"])
        print()
    print("=== mean location_coverage (higher is better; ≥0.8 target) ===")
    for name, vals in agg.items():
        print(f"  {name:8} : {round(sum(vals)/len(vals), 3)}  (n={len(vals)})")


if __name__ == "__main__":
    main()
