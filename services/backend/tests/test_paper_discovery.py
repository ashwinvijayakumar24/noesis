"""
Tests for paper extraction and discovery:
- Zotero service
- BibTeX import flow
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# ── Zotero Service Tests ──────────────────────────────────────────────────────

class TestZoteroService:
    """Tests for the Zotero integration service."""

    @pytest.mark.unit
    def test_zotero_item_to_document_journal_article(self):
        """Journal article is correctly converted to document record."""
        from app.services.zotero_service import _zotero_item_to_document_record

        item = {
            "key": "ABCD1234",
            "data": {
                "itemType": "journalArticle",
                "title": "Deep Learning for NLP",
                "creators": [
                    {"creatorType": "author", "firstName": "Yann", "lastName": "LeCun"},
                    {"creatorType": "author", "firstName": "Geoffrey", "lastName": "Hinton"},
                ],
                "date": "2015-01-01",
                "DOI": "10.1234/dl-nlp",
                "abstractNote": "We review deep learning methods...",
                "publicationTitle": "Nature",
                "volume": "521",
                "pages": "436-444",
            }
        }

        record = _zotero_item_to_document_record(item, "user-id", "project-id")

        assert record is not None
        assert record["title"] == "Deep Learning for NLP"
        assert record["user_id"] == "user-id"
        assert record["project_id"] == "project-id"
        assert record["status"] == "imported"
        assert "Yann LeCun" in record["metadata"]["authors"]
        assert record["metadata"]["doi"] == "10.1234/dl-nlp"
        assert record["metadata"]["year"] == "2015"

    @pytest.mark.unit
    def test_zotero_item_to_document_skips_notes(self):
        """Notes and attachments are skipped (returns None)."""
        from app.services.zotero_service import _zotero_item_to_document_record

        note_item = {
            "key": "NOTE1",
            "data": {"itemType": "note", "note": "Some note content"}
        }
        attachment_item = {
            "key": "ATT1",
            "data": {"itemType": "attachment", "title": "paper.pdf"}
        }

        assert _zotero_item_to_document_record(note_item, "u", "p") is None
        assert _zotero_item_to_document_record(attachment_item, "u", "p") is None

    @pytest.mark.unit
    def test_zotero_item_to_document_skips_no_title(self):
        """Items without a title are skipped."""
        from app.services.zotero_service import _zotero_item_to_document_record

        item = {
            "key": "NT1",
            "data": {"itemType": "journalArticle", "title": ""}
        }

        assert _zotero_item_to_document_record(item, "u", "p") is None

    @pytest.mark.unit
    @patch("aiohttp.ClientSession")
    async def test_validate_api_key_valid(self, mock_session_cls):
        """Valid API key returns user info."""
        from app.services.zotero_service import validate_api_key

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "key": "testkey123",
            "user": {"id": 12345, "username": "researcher", "name": "Dr. Smith"},
            "access": {"user": {"library": True}}
        })

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        info = await validate_api_key("testkey123")

        assert info is not None
        assert info["user_id"] == 12345
        assert info["username"] == "researcher"

    @pytest.mark.unit
    @patch("aiohttp.ClientSession")
    async def test_validate_api_key_invalid(self, mock_session_cls):
        """404 response returns None (invalid key)."""
        from app.services.zotero_service import validate_api_key

        mock_response = MagicMock()
        mock_response.status = 404

        mock_session = MagicMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_session_cls.return_value = mock_session

        info = await validate_api_key("invalid-key")
        assert info is None


# ── BibTeX Import Tests ───────────────────────────────────────────────────────

class TestBibtexImport:
    """Tests for BibTeX import with DOI/Unpaywall integration."""

    @pytest.mark.unit
    def test_parse_bibtex_basic(self):
        """BibTeX parser returns expected entries."""
        from app.services.citation_management import parse_bibtex_file

        bibtex_content = """
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam},
  journal={NeurIPS},
  year={2017},
  doi={10.48550/arXiv.1706.03762}
}
        """

        entries = parse_bibtex_file(bibtex_content)

        assert len(entries) == 1
        assert entries[0]["title"] == "Attention Is All You Need"
        assert entries[0]["year"] == "2017"

    @pytest.mark.unit
    def test_parse_bibtex_empty_returns_empty_list(self):
        """Empty BibTeX content returns empty list."""
        from app.services.citation_management import parse_bibtex_file

        assert parse_bibtex_file("") == []
        assert parse_bibtex_file("% Just a comment") == []
