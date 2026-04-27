"""
Document Analysis Service
Provides AI-powered structured analysis of research papers using GPT-5.2.
"""

import json
import time
from typing import Dict, Any, Optional
from app.core.openai_client import get_openai_client, get_completion_params
from app.core.logging_config import get_logger
from app.services.retry_utils import retry_openai

logger = get_logger(__name__)

# Initialize OpenAI client with privacy-first configuration
client = get_openai_client()


@retry_openai
def _create_chat_completion(**kwargs):
    return client.chat.completions.create(**kwargs)


# Analysis tiers based on page count
ANALYSIS_TIERS = {
    "SHORT": {"page_range": (1, 3), "max_tokens": 1500},    # Posters, extended abstracts
    "MEDIUM": {"page_range": (4, 15), "max_tokens": 3000},  # Standard conference/journal papers
    "LONG": {"page_range": (16, float('inf')), "max_tokens": 4000}  # Surveys, dissertations, theses
}


def get_analysis_tier(page_count: int) -> str:
    """Determine analysis tier based on page count."""
    for tier_name, config in ANALYSIS_TIERS.items():
        min_pages, max_pages = config["page_range"]
        if min_pages <= page_count <= max_pages:
            return tier_name
    return "SHORT"  # Fallback


# SHORT TIER: Basic analysis for 1-5 page papers
ANALYSIS_PROMPT_SHORT = """You are an expert research paper analyzer. Your task is to read a research paper and extract structured information.

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


# MEDIUM TIER: Detailed analysis for 6-15 page papers (2-3x more detail)
ANALYSIS_PROMPT_MEDIUM = """You are an expert research paper analyzer. Your task is to read a research paper and extract comprehensive structured information.

You must respond with ONLY a valid JSON object. Do not include any explanatory text before or after the JSON.

The JSON must follow this exact structure:
{
  "executive_summary": "2-3 paragraph comprehensive overview covering: main contribution, methodology, and key results",
  "research_problem": "Detailed description of the problem, including context and why it's important",
  "key_questions": ["Research question 1", "Research question 2", "Research question 3", "Research question 4"],
  "methodology": {
    "approach": "Comprehensive description of the overall methodology and experimental design",
    "techniques": [
      "Technique 1 with specific parameters/details",
      "Technique 2 with specific parameters/details",
      "Technique 3 with specific parameters/details",
      "Technique 4 with specific parameters/details"
    ],
    "algorithms": ["Algorithm 1 (e.g., TextBlob with specific config)", "Algorithm 2 with parameters"],
    "dataset": "Detailed dataset description including: name, size (e.g., 77,332 samples), source, preprocessing steps",
    "baselines": ["Baseline method 1 compared against", "Baseline method 2 compared against"],
    "evaluation_metrics": ["Metric 1 (e.g., accuracy, F1-score)", "Metric 2", "Metric 3"]
  },
  "key_findings": [
    "Finding 1 with specific numbers/results (e.g., achieved 71% accuracy)",
    "Finding 2 with specific numbers/results",
    "Finding 3 with specific numbers/results",
    "Finding 4 with specific numbers/results",
    "Finding 5 with specific numbers/results",
    "Finding 6 with specific numbers/results",
    "Finding 7 with specific numbers/results"
  ],
  "results": {
    "summary": "Comprehensive overview of results with specific performance numbers",
    "metrics": [
      "Metric 1: specific value (e.g., SVC: 71% accuracy)",
      "Metric 2: specific value (e.g., Random Forest: 66% accuracy)",
      "Metric 3: specific value",
      "Metric 4: specific value",
      "Metric 5: specific value"
    ],
    "comparisons": ["Comparison with baseline 1: performance difference", "Comparison with baseline 2: performance difference"]
  },
  "novel_contributions": [
    "What's new contribution 1 vs prior work",
    "What's new contribution 2 vs prior work",
    "What's new contribution 3 vs prior work"
  ],
  "limitations": [
    "Specific limitation 1",
    "Specific limitation 2",
    "Specific limitation 3",
    "Specific limitation 4",
    "Specific limitation 5"
  ],
  "future_work": [
    "Concrete future direction 1",
    "Concrete future direction 2",
    "Concrete future direction 3",
    "Concrete future direction 4"
  ],
  "key_citations": [
    {
      "authors": "First author et al.",
      "year": "2023",
      "title": "Citation title",
      "relevance": "Detailed explanation of why this citation is important"
    }
  ]
}

Guidelines:
- Be VERY DETAILED - include specific numbers, dataset names, algorithm names, performance metrics
- For methodology: Include specific algorithm names (e.g., "TextBlob", "VADER", "SentiWordNet"), parameter settings, dataset sizes
- For findings: ALWAYS include specific performance numbers, percentages, metrics (e.g., "71% accuracy", "66% F1-score")
- For datasets: Include exact names, sizes (e.g., "77,332 tweets from 10 UK cities"), and sources
- Extract 5-7 key findings minimum, not just 3
- Extract 4-5 specific limitations, not just 2
- Include novel contributions vs prior work
- Include baseline comparisons with specific performance differences
- Extract actual data from the paper, don't make things up
- If a section is not applicable or not found, use an empty array [] or "Not mentioned in the paper"
- For citations, include the most influential/relevant ones (max 7)
"""


# LONG TIER: Very comprehensive analysis for 16+ page papers (3-4x more detail)
ANALYSIS_PROMPT_LONG = """You are an expert research paper analyzer. Your task is to read a research paper and extract highly comprehensive structured information.

You must respond with ONLY a valid JSON object. Do not include any explanatory text before or after the JSON.

The JSON must follow this exact structure:
{
  "executive_summary": "3-4 paragraph very comprehensive overview covering: problem context, main contribution, detailed methodology, key results, and significance",
  "research_problem": "Very detailed description of the problem, including: background, context, why it's important, gaps in prior work, and research motivation",
  "key_questions": ["Research question 1", "Research question 2", "Research question 3", "Research question 4", "Research question 5", "Research question 6"],
  "methodology": {
    "approach": "Very comprehensive description of the overall methodology, experimental design, and research workflow",
    "techniques": [
      "Technique 1 with detailed parameters, justification, and configuration",
      "Technique 2 with detailed parameters, justification, and configuration",
      "Technique 3 with detailed parameters, justification, and configuration",
      "Technique 4 with detailed parameters, justification, and configuration",
      "Technique 5 with detailed parameters, justification, and configuration",
      "Technique 6 with detailed parameters, justification, and configuration"
    ],
    "algorithms": [
      "Algorithm 1 with detailed parameters and configuration",
      "Algorithm 2 with detailed parameters and configuration",
      "Algorithm 3 with detailed parameters and configuration"
    ],
    "dataset": "Very detailed dataset description including: name, exact size, source, collection method, preprocessing steps, train/test split, validation strategy",
    "baselines": [
      "Baseline method 1 with description",
      "Baseline method 2 with description",
      "Baseline method 3 with description",
      "Baseline method 4 with description"
    ],
    "evaluation_metrics": [
      "Metric 1 with explanation of why chosen",
      "Metric 2 with explanation",
      "Metric 3 with explanation",
      "Metric 4 with explanation"
    ],
    "implementation_details": [
      "Detail 1 (e.g., programming language, libraries, hardware)",
      "Detail 2",
      "Detail 3"
    ]
  },
  "key_findings": [
    "Finding 1 with specific numbers, confidence intervals, statistical significance",
    "Finding 2 with specific numbers, confidence intervals, statistical significance",
    "Finding 3 with specific numbers, confidence intervals, statistical significance",
    "Finding 4 with specific numbers, confidence intervals, statistical significance",
    "Finding 5 with specific numbers, confidence intervals, statistical significance",
    "Finding 6 with specific numbers, confidence intervals, statistical significance",
    "Finding 7 with specific numbers, confidence intervals, statistical significance",
    "Finding 8 with specific numbers, confidence intervals, statistical significance",
    "Finding 9 with specific numbers, confidence intervals, statistical significance",
    "Finding 10 with specific numbers, confidence intervals, statistical significance"
  ],
  "results": {
    "summary": "Very comprehensive overview of all results with detailed performance analysis",
    "metrics": [
      "Metric 1: specific value with context (e.g., SVC: 71% accuracy on test set)",
      "Metric 2: specific value with context",
      "Metric 3: specific value with context",
      "Metric 4: specific value with context",
      "Metric 5: specific value with context",
      "Metric 6: specific value with context",
      "Metric 7: specific value with context",
      "Metric 8: specific value with context"
    ],
    "comparisons": [
      "Comparison with baseline 1: detailed performance difference with statistical significance",
      "Comparison with baseline 2: detailed performance difference",
      "Comparison with baseline 3: detailed performance difference",
      "Comparison with prior work: how this work improves"
    ],
    "ablation_studies": ["Ablation result 1", "Ablation result 2", "Ablation result 3"]
  },
  "novel_contributions": [
    "Novel contribution 1 with detailed explanation of novelty vs prior work",
    "Novel contribution 2 with detailed explanation",
    "Novel contribution 3 with detailed explanation",
    "Novel contribution 4 with detailed explanation"
  ],
  "limitations": [
    "Detailed limitation 1 with implications",
    "Detailed limitation 2 with implications",
    "Detailed limitation 3 with implications",
    "Detailed limitation 4 with implications",
    "Detailed limitation 5 with implications",
    "Detailed limitation 6 with implications"
  ],
  "future_work": [
    "Concrete future direction 1 with justification",
    "Concrete future direction 2 with justification",
    "Concrete future direction 3 with justification",
    "Concrete future direction 4 with justification",
    "Concrete future direction 5 with justification"
  ],
  "critical_assessment": {
    "strengths": ["Strength 1", "Strength 2", "Strength 3"],
    "weaknesses": ["Weakness 1", "Weakness 2", "Weakness 3"],
    "impact": "Assessment of potential impact on the field"
  },
  "key_citations": [
    {
      "authors": "First author et al.",
      "year": "2023",
      "title": "Citation title",
      "relevance": "Very detailed explanation of why this citation is important and how it relates to this work"
    }
  ]
}

Guidelines:
- Be EXTREMELY DETAILED - this is a long paper, extract comprehensive information
- Include ALL specific numbers, dataset names, algorithm names, performance metrics, statistical significance
- For methodology: Include specific algorithm names, all parameter settings, dataset sizes, train/test splits, validation strategies
- For findings: ALWAYS include 8-10 detailed findings with specific numbers, percentages, metrics, and statistical significance
- For datasets: Include exact names, sizes, sources, collection methods, preprocessing steps
- Extract 8-10 key findings minimum with detailed performance numbers
- Extract 5-6 specific limitations with implications
- Include detailed novel contributions vs prior work (4+ contributions)
- Include baseline comparisons with specific performance differences and statistical significance
- Include ablation study results if available
- Include critical assessment of strengths, weaknesses, and impact
- Extract actual data from the paper, don't make things up
- If a section is not applicable or not found, use an empty array [] or "Not mentioned in the paper"
- For citations, include the most influential/relevant ones (max 10)
"""


def analyze_paper_text(paper_text: str, page_count: int = 10, model: str = "gpt-5.2-chat-latest") -> Dict[str, Any]:
    """
    Analyze a research paper using GPT-5.2 and return structured analysis.

    Uses adaptive analysis depth based on paper length:
    - SHORT (1-5 pages): Basic analysis
    - MEDIUM (6-15 pages): 2-3x more detailed analysis
    - LONG (16+ pages): 3-4x more detailed analysis

    Args:
        paper_text: The full text content of the paper
        page_count: Number of pages in the paper (default: 10 for MEDIUM tier)
        model: OpenAI model to use (default: gpt-4o)

    Returns:
        Dictionary containing structured analysis with tier-appropriate detail

    Raises:
        Exception: If analysis fails
    """
    start_time = time.time()

    try:
        # Determine analysis tier based on page count
        tier = get_analysis_tier(page_count)
        tier_config = ANALYSIS_TIERS[tier]
        max_tokens = tier_config["max_tokens"]

        # Select appropriate prompt based on tier
        if tier == "SHORT":
            system_prompt = ANALYSIS_PROMPT_SHORT
        elif tier == "MEDIUM":
            system_prompt = ANALYSIS_PROMPT_MEDIUM
        else:  # LONG
            system_prompt = ANALYSIS_PROMPT_LONG

        logger.info(f"Starting analysis with model: {model}, tier: {tier}, page_count: {page_count}")
        logger.info(f"Paper text length: {len(paper_text)} characters")
        logger.info(f"Max tokens for tier {tier}: {max_tokens}")

        # Truncate paper text to fit within token limits
        # OpenAI TPM limit: 30,000 tokens/min for gpt-4o
        # Reserve tokens: max_tokens (output) + ~2000 (prompt/overhead)
        # Available for input: 30000 - max_tokens - 2000 ≈ 24,000 tokens
        # Convert to characters: ~96,000 chars (4 chars per token)
        max_input_chars = 96000

        if len(paper_text) > max_input_chars:
            logger.warning(f"Truncating paper text from {len(paper_text)} to {max_input_chars} characters to fit token limits")
            truncated_text = paper_text[:max_input_chars] + "\n\n[... content truncated to fit within API token limits ...]"
        else:
            truncated_text = paper_text

        # Call OpenAI API - GPT-5.2 relies on explicit JSON instructions in prompts
        # Note: GPT-5.2-chat-latest only supports temperature=1.0 (default)
        response = _create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze this research paper and respond ONLY with valid JSON (no markdown, no code blocks):\n\n{truncated_text}"}
            ],
            max_completion_tokens=max_tokens,  # GPT-5.2 uses max_completion_tokens
            **get_completion_params()  # Enable zero data retention
        )

        # Extract and parse the JSON response
        analysis_json = response.choices[0].message.content

        if not analysis_json:
            logger.warning("GPT response returned empty content")

        if not analysis_json or analysis_json.strip() == "":
            raise ValueError("GPT-5.2 returned empty response. Check prompt engineering - ensure explicit JSON instructions are clear.")

        analysis = json.loads(analysis_json)

        # Add metadata including tier information
        processing_time = time.time() - start_time
        analysis["analysis_metadata"] = {
            "model": model,
            "page_count": page_count,
            "analysis_tier": tier,
            "max_tokens_allowed": max_tokens,
            "processing_time_seconds": round(processing_time, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tokens_used": response.usage.total_tokens if response.usage else None,
            "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
            "completion_tokens": response.usage.completion_tokens if response.usage else None
        }

        logger.info(f"Completed in {processing_time:.2f}s (tier: {tier})")
        logger.info(f"Tokens used: {response.usage.total_tokens if response.usage else 'unknown'}")

        return analysis

    except json.JSONDecodeError as e:
        logger.error("Failed to parse JSON response from model")
        raise Exception(f"Failed to parse analysis response as JSON: {e}")

    except Exception as e:
        logger.error(f"Analysis failed: {type(e).__name__}")
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

        # Use GPT-5-mini to extract citation info - relies on explicit JSON instructions
        # Note: Removing temperature parameter to use model defaults
        response = _create_chat_completion(
            model="gpt-5-mini",  # Use mini for speed/cost
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
                    "content": f"Extract citation metadata from this paper (look at the first 2000 characters) and respond ONLY with valid JSON:\n\n{paper_text[:2000]}"
                }
            ],
            max_completion_tokens=200,
            **get_completion_params()  # Enable zero data retention
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
