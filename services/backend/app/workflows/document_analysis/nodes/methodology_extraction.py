"""
Methodology Extraction Node

Extracts methodological details from research papers:
- Algorithms and techniques used
- Datasets and data sources
- Experimental design
- Evaluation metrics
- Parameters and hyperparameters

This enables cross-paper methodological comparison and reproducibility assessment.
"""

from typing import List
from app.workflows.document_analysis.state import DocumentAnalysisState, Method
from app.core.logging_config import get_logger
from app.core.openai_client import get_openai_client, get_completion_params
import json

logger = get_logger(__name__)
client = get_openai_client()


METHODOLOGY_EXTRACTION_PROMPT = """You are an expert at extracting research methodology from academic papers.

Extract ALL significant methodological details from the provided document:
- Algorithms and techniques
- Datasets and data sources
- Experimental design approaches
- Evaluation metrics
- Statistical methods
- Parameters and hyperparameters (if specified)

Return ONLY a valid JSON object:
{
  "methods": [
    {
      "method_name": "BERT fine-tuning",
      "method_type": "algorithm",
      "description": "Fine-tuned BERT-base model on sentiment classification task",
      "parameters": {
        "learning_rate": 0.00001,
        "batch_size": 32,
        "epochs": 3,
        "optimizer": "AdamW"
      },
      "section_title": "Methodology",
      "datasets_used": ["IMDB", "SST-2"],
      "evaluation_metrics": ["accuracy", "F1-score", "precision", "recall"]
    },
    {
      "method_name": "Random Forest baseline",
      "method_type": "algorithm",
      "description": "Traditional ML baseline using bag-of-words features",
      "parameters": {
        "n_estimators": 100,
        "max_depth": 10
      },
      "section_title": "Baselines",
      "datasets_used": ["IMDB"],
      "evaluation_metrics": ["accuracy", "F1-score"]
    },
    {
      "method_name": "10-fold cross-validation",
      "method_type": "experimental_design",
      "description": "Evaluation using stratified 10-fold cross-validation",
      "parameters": {},
      "section_title": "Experimental Setup",
      "datasets_used": [],
      "evaluation_metrics": []
    }
  ]
}

Method types:
- algorithm: ML/AI algorithms, models, techniques
- experimental_design: Study design, validation strategies, sampling methods
- data_collection: How data was gathered or created
- statistical_analysis: Statistical tests, hypothesis testing methods

Extract 5-15 methods. Include parameters only if explicitly stated in the paper.
"""


def extract_methodology_node(state: DocumentAnalysisState) -> DocumentAnalysisState:
    """
    Extract methodology and experimental details from the document.

    Args:
        state: Current workflow state

    Returns:
        Updated state with extracted methods
    """
    logger.info(f"[DOC-METHODS] Starting methodology extraction for document_id={state['document_id']}")

    try:
        document_text = state["document_text"]
        structure = state.get("structure", {})

        # Focus on methodology section if available, otherwise use broader context
        has_methods_section = structure.get("has_methods", False)

        if has_methods_section:
            # Analyze full document but emphasize methods section
            analysis_text = document_text[:20000]
            logger.info(f"[DOC-METHODS] Document has methods section, analyzing {len(analysis_text)} chars")
        else:
            # Short papers might not have explicit methods section
            analysis_text = document_text[:15000]
            logger.info(f"[DOC-METHODS] No explicit methods section, analyzing {len(analysis_text)} chars")

        # Call GPT-4o to extract methodology
        logger.info(f"[DOC-METHODS] Calling GPT-4o for methodology extraction...")
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": METHODOLOGY_EXTRACTION_PROMPT},
                {
                    "role": "user",
                    "content": f"Extract methodology from this document:\n\nTitle: {structure.get('title', 'Unknown')}\n\n{analysis_text}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=2500,
            **get_completion_params()  # Enable zero data retention
        )

        result = json.loads(response.choices[0].message.content)
        methods_data = result.get("methods", [])

        logger.info(f"[DOC-METHODS] ✓ Extracted {len(methods_data)} methods")

        # Convert to typed Method objects
        methods: List[Method] = []
        for method_data in methods_data:
            method: Method = {
                "method_name": method_data.get("method_name", ""),
                "method_type": method_data.get("method_type"),
                "description": method_data.get("description", ""),
                "parameters": method_data.get("parameters", {}),
                "section_title": method_data.get("section_title"),
                "page_number": method_data.get("page_number"),
                "datasets_used": method_data.get("datasets_used", []),
                "evaluation_metrics": method_data.get("evaluation_metrics", [])
            }
            methods.append(method)

        # Group methods by type
        methods_by_type = {}
        for method in methods:
            method_type = method.get("method_type", "other")
            if method_type not in methods_by_type:
                methods_by_type[method_type] = []
            methods_by_type[method_type].append(method)

        # Log summary
        logger.info(f"[DOC-METHODS] Methods by type: {dict((k, len(v)) for k, v in methods_by_type.items())}")

        # Extract unique datasets and metrics for summary
        all_datasets = set()
        all_metrics = set()
        for method in methods:
            all_datasets.update(method.get("datasets_used", []))
            all_metrics.update(method.get("evaluation_metrics", []))

        logger.info(f"[DOC-METHODS] Datasets: {list(all_datasets)[:5]}")  # Show first 5
        logger.info(f"[DOC-METHODS] Metrics: {list(all_metrics)[:5]}")  # Show first 5

        return {
            **state,
            "methods": methods,
            "methods_by_type": methods_by_type,
            "current_step": "Methodology Extraction",
            "progress_percentage": 60
        }

    except Exception as e:
        logger.error(f"[DOC-METHODS] Error extracting methodology: {e}")
        errors = state.get("errors", [])
        errors.append(f"Methodology extraction failed: {str(e)}")

        return {
            **state,
            "errors": errors,
            "current_step": "Methodology Extraction (Failed)",
            "progress_percentage": 60
        }
