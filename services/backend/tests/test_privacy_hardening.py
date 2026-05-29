import json


def test_openai_completion_params_disable_storage_by_default():
    from app.core.openai_client import get_completion_params

    params = get_completion_params()

    assert params["store"] is False


def test_workflow_checkpoint_minimization_removes_manuscript_content():
    from app.core.privacy import minimize_workflow_checkpoint

    state = {
        "draft_id": "draft-1",
        "project_id": "project-1",
        "user_id": "user-1",
        "draft_content": "This is an unpublished manuscript with novel results.",
        "claims": [{"claim_text": "Novel unpublished finding"}],
        "reviewer_feedback": [{"feedback_text": "Quoted draft sentence"}],
        "current_step": "Reviewer Panel",
        "progress_percentage": 80,
    }

    minimized = minimize_workflow_checkpoint(state)
    serialized = json.dumps(minimized)

    assert minimized["privacy_minimized"] is True
    assert "draft_content" not in minimized
    assert "unpublished manuscript" not in serialized
    assert "Novel unpublished finding" not in serialized
    assert minimized["counts"]["claims"] == 1
    assert minimized["counts"]["reviewer_feedback"] == 1


def test_structure_storage_strips_raw_section_and_paragraph_text():
    from app.core.privacy import strip_manuscript_content_from_structure

    structure = {
        "sections": [
            {
                "id": "s1",
                "title": "Results",
                "type": "results",
                "content": "Private unpublished result text.",
                "paragraphs": [{"text": "Private paragraph."}],
            }
        ],
        "word_count": 4,
    }

    stripped = strip_manuscript_content_from_structure(structure)
    serialized = json.dumps(stripped)

    assert "content" not in stripped["sections"][0]
    assert "paragraphs" not in stripped["sections"][0]
    assert "Private unpublished" not in serialized
    assert stripped["sections"][0]["title"] == "Results"
