import pytest


class TestDocumentMetadataNormalization:
    @pytest.mark.unit
    def test_normalizes_grobid_author_objects(self):
        from app.services.document_metadata import normalize_grobid_metadata

        result = normalize_grobid_metadata({
            "title": "A Strong Paper",
            "abstract": "This paper studies something.",
            "authors": [
                {"first_name": "Ada", "last_name": "Lovelace"},
                {"first_name": "Grace", "middle_name": "B.", "last_name": "Hopper"},
            ],
            "metadata": {"publication_date": "2024-03-01", "journal": "Journal of Tests"},
        })

        assert result["title"] == "A Strong Paper"
        assert result["authors"] == ["Ada Lovelace", "Grace B. Hopper"]
        assert result["year"] == "2024"
        assert result["journal"] == "Journal of Tests"
        assert result["metadata_status"] == "extracted"

    @pytest.mark.unit
    def test_promotes_extracted_title_for_filename_like_title(self):
        from app.services.document_metadata import build_document_update

        update = build_document_update(
            "s41467-021-20910-4.pdf",
            {"original_filename": "s41467-021-20910-4.pdf"},
            {"extracted_title": "Machine Learning for Clinical Review", "title": "Machine Learning for Clinical Review"},
        )

        assert update["title"] == "Machine Learning for Clinical Review"
        assert update["metadata"]["extracted_title"] == "Machine Learning for Clinical Review"

    @pytest.mark.unit
    def test_preserves_user_edited_title(self):
        from app.services.document_metadata import build_document_update

        update = build_document_update(
            "My advisor's favorite paper",
            {"original_filename": "s41467-021-20910-4.pdf"},
            {"extracted_title": "Machine Learning for Clinical Review", "title": "Machine Learning for Clinical Review"},
        )

        assert "title" not in update
        assert update["metadata"]["extracted_title"] == "Machine Learning for Clinical Review"

    @pytest.mark.unit
    def test_external_metadata_fills_missing_fields_without_overwriting(self):
        from app.services.document_metadata import merge_metadata

        merged = merge_metadata(
            {
                "authors": ["Local Author"],
                "metadata_source": "grobid",
                "metadata_confidence": 0.82,
            },
            {
                "authors": ["External Author"],
                "year": "2023",
                "journal": "External Journal",
                "metadata_source": "openalex",
                "metadata_confidence": 0.9,
            },
        )

        assert merged["authors"] == ["Local Author"]
        assert merged["year"] == "2023"
        assert merged["journal"] == "External Journal"
        assert merged["metadata_source"] == "openalex"
