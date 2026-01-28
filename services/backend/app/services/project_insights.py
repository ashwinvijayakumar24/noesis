"""
Project Insights Analysis Service

Analyzes all documents in a project to identify:
- Research gaps (methodological, population, theoretical, temporal)
- Common themes across papers
- Methodological patterns
- Timeline and evolution of ideas
- Conflicting findings
- Citation patterns
"""

from openai import OpenAI
import os
from typing import List, Dict, Any
import json

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

INSIGHTS_SYSTEM_PROMPT = """You are an expert research analyst. Analyze a collection of research paper summaries to identify cross-paper patterns, gaps, and insights.

Your task is to produce a comprehensive analysis in JSON format with the following structure:

{
  "research_gaps": [
    {
      "category": "methodological" | "population" | "theoretical" | "temporal",
      "title": "Brief title of the gap",
      "description": "Detailed description of what hasn't been studied",
      "supporting_evidence": ["Evidence from the papers that this is indeed a gap"],
      "suggested_directions": ["Specific research directions to address this gap"]
    }
  ],
  "common_themes": [
    {
      "theme": "Name of the theme",
      "frequency": <number of papers with this theme>,
      "description": "Description of how this theme appears across papers",
      "paper_titles": ["List of paper titles that include this theme"]
    }
  ],
  "methodological_patterns": [
    {
      "methodology": "Name of methodology",
      "usage_count": <number of papers using this>,
      "description": "How this methodology is applied",
      "variations": ["Different variations or approaches"]
    }
  ],
  "timeline": [
    {
      "period": "Description of time period or progression",
      "development": "What changed or developed",
      "papers": ["Papers representing this period/development"]
    }
  ],
  "conflicting_findings": [
    {
      "topic": "What the conflict is about",
      "side_a": {
        "position": "First position",
        "papers": ["Papers supporting this"],
        "evidence": "Summary of evidence"
      },
      "side_b": {
        "position": "Opposing position",
        "papers": ["Papers supporting this"],
        "evidence": "Summary of evidence"
      },
      "resolution": "Possible explanation for the conflict or which side has stronger evidence"
    }
  ],
  "citation_patterns": [
    {
      "cited_work": "Author/title of frequently cited work",
      "frequency": <how many papers cite it>,
      "context": "Why this work is important/frequently cited",
      "papers_citing": ["Papers that cite this work"]
    }
  ],
  "key_insights": [
    "High-level insight 1",
    "High-level insight 2",
    "High-level insight 3"
  ],
  "summary": "Overall summary of the body of literature (2-3 sentences)"
}

IMPORTANT GUIDELINES:
1. For research_gaps, be specific and actionable. Look for:
   - Methodological gaps: Missing research methods, data types, analytical approaches
   - Population gaps: Understudied demographics, regions, contexts
   - Theoretical gaps: Missing theoretical frameworks or perspectives
   - Temporal gaps: Missing time periods, lack of longitudinal studies
2. Only include gaps that are clearly evident from the papers
3. For common_themes, identify patterns that appear in 2+ papers
4. For conflicting_findings, only include if there are genuine disagreements
5. Be precise with paper titles when referencing them
6. Provide evidence-based analysis, not speculation
7. If a section has no relevant findings, return an empty array []

Return ONLY valid JSON, no other text."""


def analyze_project_insights(document_analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Analyze multiple document analyses to extract cross-paper insights.

    Now enhanced with LangGraph-extracted structured data for richer context!

    Args:
        document_analyses: List of document analysis objects, each containing:
            - title: Document title
            - analysis: The GPT-4o analysis with executive_summary, methodology, etc.
            - document_id: UUID to fetch structured claims/methods/findings

    Returns:
        Dictionary containing insights across all papers
    """
    from app.core.supabase_client import supabase

    if not document_analyses or len(document_analyses) == 0:
        raise ValueError("No document analyses provided")

    # Build context from all document analyses
    papers_context = []
    for i, doc in enumerate(document_analyses, 1):
        title = doc.get('title', f'Document {i}')
        document_id = doc.get('id')  # Need document ID to fetch structured data
        analysis = doc.get('analysis', {})

        # Fetch LangGraph-extracted structured data for richer context
        structured_claims = []
        structured_methods = []
        structured_findings = []

        if document_id:
            try:
                # Fetch claims (top 10 most important)
                claims_res = supabase.table("document_claims").select("claim_text, claim_type, importance_score").eq("document_id", document_id).order("importance_score", desc=True).limit(10).execute()
                structured_claims = [f"{c['claim_text']} [{c['claim_type']}]" for c in claims_res.data] if claims_res.data else []

                # Fetch methods (top 8)
                methods_res = supabase.table("document_methods").select("method_name, method_type, description, datasets_used, evaluation_metrics").eq("document_id", document_id).limit(8).execute()
                structured_methods = []
                for m in (methods_res.data if methods_res.data else []):
                    method_str = f"{m['method_name']}"
                    if m.get('method_type'):
                        method_str += f" ({m['method_type']})"
                    if m.get('datasets_used'):
                        method_str += f" - Datasets: {', '.join(m['datasets_used'][:3])}"
                    if m.get('evaluation_metrics'):
                        method_str += f" - Metrics: {', '.join(m['evaluation_metrics'][:3])}"
                    structured_methods.append(method_str)

                # Fetch findings (top 10 with metrics)
                findings_res = supabase.table("document_findings").select("finding_text, finding_type, metrics, comparison_baseline").eq("document_id", document_id).order("confidence_score", desc=True).limit(10).execute()
                structured_findings = []
                for f in (findings_res.data if findings_res.data else []):
                    finding_str = f['finding_text']
                    if f.get('metrics'):
                        finding_str += f" (Metrics: {f['metrics']})"
                    if f.get('comparison_baseline'):
                        finding_str += f" vs. {f['comparison_baseline']}"
                    structured_findings.append(finding_str)
            except Exception as e:
                print(f"[INSIGHTS] Warning: Could not fetch structured data for {title}: {e}")
                # Continue without structured data if fetch fails

        # Build comprehensive paper summary with both traditional and structured data
        paper_summary = f"""
Paper {i}: {title}

Executive Summary:
{analysis.get('executive_summary', 'N/A')}

Research Problem:
{analysis.get('research_problem', 'N/A')}

Methodology:
- Approach: {analysis.get('methodology', {}).get('approach', 'N/A')}
- Techniques: {', '.join(analysis.get('methodology', {}).get('techniques', []))}
- Dataset: {analysis.get('methodology', {}).get('dataset', 'N/A')}
"""

        # Add structured methods if available (LangGraph data)
        if structured_methods:
            paper_summary += f"""
Structured Methods Extracted (LangGraph):
{chr(10).join('- ' + m for m in structured_methods)}
"""

        paper_summary += f"""
Key Findings:
{chr(10).join('- ' + f for f in analysis.get('key_findings', []))}
"""

        # Add structured findings if available (LangGraph data)
        if structured_findings:
            paper_summary += f"""
Structured Quantitative Findings (LangGraph):
{chr(10).join('- ' + f for f in structured_findings)}
"""

        # Add structured claims if available (LangGraph data)
        if structured_claims:
            paper_summary += f"""
Key Claims Extracted (LangGraph):
{chr(10).join('- ' + c for c in structured_claims[:8])}
"""

        paper_summary += f"""
Results Summary:
{analysis.get('results', {}).get('summary', 'N/A')}

Limitations:
{chr(10).join('- ' + l for l in analysis.get('limitations', []))}

Future Work:
{chr(10).join('- ' + fw for fw in analysis.get('future_work', []))}

Key Citations:
{chr(10).join(f"- {c.get('authors', 'Unknown')} ({c.get('year', 'N/A')}): {c.get('title', 'N/A')}" for c in analysis.get('key_citations', [])[:3])}
"""
        papers_context.append(paper_summary)

    # Combine all papers
    full_context = "\n\n" + "="*80 + "\n\n".join(papers_context)

    # Call OpenAI to analyze
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": INSIGHTS_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze these {len(document_analyses)} research papers and identify cross-paper insights:\n{full_context}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
        max_tokens=3000
    )

    insights_json = response.choices[0].message.content
    insights = json.loads(insights_json)

    # Add metadata
    insights['analysis_metadata'] = {
        'num_papers_analyzed': len(document_analyses),
        'model': 'gpt-4o',
        'enhanced_with_langgraph': True,  # Using structured claims/methods/findings
        'timestamp': None  # Will be set by caller
    }

    # Validate structure
    validate_insights(insights)

    return insights


def validate_insights(insights: Dict[str, Any]) -> None:
    """
    Validate that insights have the expected structure.

    Raises:
        ValueError: If insights are missing required fields
    """
    required_fields = [
        'research_gaps',
        'common_themes',
        'methodological_patterns',
        'timeline',
        'conflicting_findings',
        'citation_patterns',
        'key_insights',
        'summary'
    ]

    for field in required_fields:
        if field not in insights:
            raise ValueError(f"Missing required field: {field}")

    # Validate research_gaps structure
    if insights['research_gaps']:
        for gap in insights['research_gaps']:
            required_gap_fields = ['category', 'title', 'description', 'supporting_evidence', 'suggested_directions']
            for field in required_gap_fields:
                if field not in gap:
                    raise ValueError(f"Research gap missing field: {field}")

            valid_categories = ['methodological', 'population', 'theoretical', 'temporal']
            if gap['category'] not in valid_categories:
                raise ValueError(f"Invalid gap category: {gap['category']}. Must be one of {valid_categories}")

    # Validate common_themes structure
    if insights['common_themes']:
        for theme in insights['common_themes']:
            required_theme_fields = ['theme', 'frequency', 'description']
            for field in required_theme_fields:
                if field not in theme:
                    raise ValueError(f"Common theme missing field: {field}")

    print(f"[INSIGHTS] Validation passed. Found {len(insights['research_gaps'])} gaps, {len(insights['common_themes'])} themes")
