"""
Document Analysis Service
Provides AI-powered structured analysis of research papers using GPT-4o.
"""

import json
import time
from typing import Dict, Any, Optional
from openai import OpenAI
import os
from app.core.logging_config import get_logger

logger = get_logger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Analysis prompt template
ANALYSIS_SYSTEM_PROMPT = """You are an expert research paper analyzer. Your task is to read a research paper and extract structured information.

You must respond with ONLY a valid JSON object. Do not include any explanatory text before or after the JSON.

The JSON must follow this exact structure:
{
  "executive_summary": "2-3 sentence overview of the paper",
  "research_problem": "What problem does this paper address?",
  "key_questions": ["Research question 1", "Research question 2"],
  "methodology": {
    "approach": "High-level description of the methodology",
    "techniques": ["Technique 1", "Technique 2"],
    "dataset": "Dataset description or 'Not applicable'"
  },
  "key_findings": [
    "Finding 1",
    "Finding 2",
    "Finding 3"
  ],
  "results": {
    "summary": "Overview of key results",
    "metrics": ["Metric 1: value/description", "Metric 2: value/description"]
  },
  "limitations": ["Limitation 1", "Limitation 2"],
  "future_work": ["Future direction 1", "Future direction 2"],
  "key_citations": [
    {
      "authors": "First author et al.",
      "year": "2023",
      "title": "Citation title",
      "relevance": "Why this citation is important"
    }
  ]
}

Guidelines:
- Be concise but informative
- Extract actual data, don't make things up
- If a section is not applicable or not found, use an empty array [] or "Not mentioned in the paper"
- Focus on the most important 3-5 items for each category
- For citations, include only the most influential/relevant ones (max 5)
"""


def analyze_paper_text(paper_text: str, model: str = "gpt-4o") -> Dict[str, Any]:
    """
    Analyze a research paper using GPT-4o and return structured analysis.

    Args:
        paper_text: The full text content of the paper
        model: OpenAI model to use (default: gpt-4o)

    Returns:
        Dictionary containing structured analysis

    Raises:
        Exception: If analysis fails
    """
    start_time = time.time()

    try:
        logger.info(f"Starting analysis with model: {model}")
        logger.info(f"Paper text length: {len(paper_text)} characters")

        # Call OpenAI API with JSON mode
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze this research paper:\n\n{paper_text}"}
            ],
            response_format={"type": "json_object"},  # Force JSON output
            temperature=0.3,  # Lower temperature for more consistent output
            max_tokens=2000  # Enough for comprehensive analysis
        )

        # Extract and parse the JSON response
        analysis_json = response.choices[0].message.content
        analysis = json.loads(analysis_json)

        # Add metadata
        processing_time = time.time() - start_time
        analysis["analysis_metadata"] = {
            "model": model,
            "processing_time_seconds": round(processing_time, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tokens_used": response.usage.total_tokens if response.usage else None
        }

        logger.info(f"Completed in {processing_time:.2f}s")
        logger.info(f"Tokens used: {response.usage.total_tokens if response.usage else 'unknown'}")

        return analysis

    except json.JSONDecodeError as e:
        logger.info(f"ERROR: Failed to parse JSON response: {e}")
        raise Exception(f"Failed to parse analysis response as JSON: {e}")

    except Exception as e:
        logger.info(f"ERROR: {type(e).__name__}: {str(e)}")
        raise Exception(f"Analysis failed: {str(e)}")


def extract_citation_metadata(paper_text: str) -> Dict[str, Any]:
    """
    Extract citation metadata from a research paper for use in literature reviews.

    This function extracts:
    - First author's last name
    - Publication year
    - All authors (for full citation)

    Args:
        paper_text: The full text content of the paper

    Returns:
        Dictionary with citation metadata:
        {
            "first_author": "Smith",
            "year": "2023",
            "all_authors": ["Smith, J.", "Johnson, K.", "Williams, L."]
        }
    """
    try:
        logger.info(f"Extracting citation metadata")

        # Use GPT-4o to extract citation info
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for speed/cost
            messages=[
                {
                    "role": "system",
                    "content": """You are a citation metadata extractor. Extract author and year information from research papers.

Return ONLY valid JSON in this exact format:
{
  "first_author": "LastName",
  "year": "YYYY",
  "all_authors": ["Author1 LastName", "Author2 LastName", "Author3 LastName"]
}

Guidelines:
- first_author should be ONLY the last name of the first author
- year should be a 4-digit year string
- all_authors should be a list of author names (first initial + last name format)
- If you cannot find the information, use "Unknown" for first_author, "N/A" for year, and empty array for all_authors
- Look for this information in the title page, header, footer, or abstract section"""
                },
                {
                    "role": "user",
                    "content": f"Extract citation metadata from this paper (look at the first 2000 characters):\n\n{paper_text[:2000]}"
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=200
        )

        citation_json = response.choices[0].message.content
        citation_metadata = json.loads(citation_json)

        logger.info(f"Extracted: {citation_metadata.get('first_author')} ({citation_metadata.get('year')})")

        return citation_metadata

    except Exception as e:
        logger.info(f"ERROR extracting metadata: {e}")
        # Return default values on error
        return {
            "first_author": "Unknown",
            "year": "N/A",
            "all_authors": []
        }


def validate_analysis(analysis: Dict[str, Any]) -> bool:
    """
    Validate that the analysis contains all required fields.

    Args:
        analysis: The analysis dictionary to validate

    Returns:
        True if valid, raises exception if invalid
    """
    required_fields = [
        "executive_summary",
        "research_problem",
        "key_questions",
        "methodology",
        "key_findings",
        "results",
        "limitations",
        "future_work",
        "key_citations"
    ]

    for field in required_fields:
        if field not in analysis:
            raise ValueError(f"Missing required field: {field}")

    # Validate nested methodology structure
    if "approach" not in analysis["methodology"]:
        raise ValueError("Missing methodology.approach")

    if "summary" not in analysis["results"]:
        raise ValueError("Missing results.summary")

    logger.info(" Validation passed")
    return True


# Test function to verify the prompt works
def test_analysis_prompt():
    """
    Test the analysis prompt with a sample paper excerpt.
    This can be run independently to verify the prompt works.
    """
    sample_paper = """
    Title: Attention Is All You Need

    Abstract: The dominant sequence transduction models are based on complex recurrent or
    convolutional neural networks that include an encoder and a decoder. The best performing
    models also connect the encoder and decoder through an attention mechanism. We propose a
    new simple network architecture, the Transformer, based solely on attention mechanisms,
    dispensing with recurrence and convolutions entirely.

    Introduction: Recurrent neural networks, long short-term memory and gated recurrent neural
    networks in particular, have been firmly established as state of the art approaches in sequence
    modeling and transduction problems. The inherent sequential nature precludes parallelization
    within training examples.

    Methodology: We propose the Transformer, a model architecture eschewing recurrence and instead
    relying entirely on an attention mechanism to draw global dependencies between input and output.
    The Transformer uses stacked self-attention and point-wise, fully connected layers.

    Results: On the WMT 2014 English-to-German translation task, our model achieves 28.4 BLEU.
    On the WMT 2014 English-to-French translation task, our model establishes a new single-model
    state-of-the-art BLEU score of 41.0.
    """

    # print("="*80)
    print("TESTING ANALYSIS PROMPT")
    # print("="*80)

    try:
        analysis = analyze_paper_text(sample_paper)
        print("\n" + "="*80)
        print("ANALYSIS RESULT:")
        # print("="*80)
        # print(json.dumps(analysis, indent=2))

        validate_analysis(analysis)

        print("\n" + "="*80)
        # print("✅ TEST PASSED: Analysis prompt works correctly")
        # print("="*80)

        return analysis

    except Exception as e:
        print("\n" + "="*80)
        print(f"❌ TEST FAILED: {e}")
        # print("="*80)
        raise


if __name__ == "__main__":
    # Run test when script is executed directly
    test_analysis_prompt()
