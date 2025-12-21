"""
Literature Review Generation Service

Generates structured literature reviews with proper author-year citations.
Supports multiple review structures: chronological, thematic, and methodological.
"""

from openai import OpenAI
import os
from typing import List, Dict, Any, Optional
import json

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Template definitions for different review structures
REVIEW_TEMPLATES = {
    "chronological": {
        "name": "Chronological Review",
        "description": "Organizes literature by publication date, showing the evolution of research over time",
        "system_prompt": """You are an expert academic writer specializing in literature reviews.

Write a chronological literature review that traces the development of research over time.

Structure:
1. Start with earlier works and progress to more recent publications
2. Show how ideas, methods, and findings have evolved
3. Identify turning points or paradigm shifts
4. Connect earlier work to later developments

Citation format:
- Use [Author, Year] format for citations
- Example: "Smith [Smith, 2020] found that..."
- For multiple authors: [Smith et al., 2020]
- Place citations immediately after the relevant statement

Writing style:
- Academic but accessible
- Use transitions to show temporal relationships ("Subsequently...", "Building on this work...", "More recently...")
- Synthesize findings, don't just list them
- Target length: {target_words} words

IMPORTANT: Use ONLY the papers provided in the context. Cite sources using the [Author, Year] format provided."""
    },

    "thematic": {
        "name": "Thematic Review",
        "description": "Organizes literature by themes or topics, regardless of chronology",
        "system_prompt": """You are an expert academic writer specializing in literature reviews.

Write a thematic literature review that organizes research by major themes or topics.

Structure:
1. Identify 3-5 major themes from the literature
2. Organize content by theme, not chronology
3. Within each theme, synthesize findings across studies
4. Show relationships and contrasts between themes

Citation format:
- Use [Author, Year] format for citations
- Example: "Several studies [Smith, 2020; Jones, 2021] have shown..."
- For multiple citations, separate with semicolons
- Place citations immediately after the relevant statement

Writing style:
- Academic but accessible
- Use clear theme headings or transitions
- Compare and contrast findings within themes
- Synthesize across studies
- Target length: {target_words} words

IMPORTANT: Use ONLY the papers provided in the context. Cite sources using the [Author, Year] format provided."""
    },

    "methodological": {
        "name": "Methodological Review",
        "description": "Organizes literature by research methods and approaches used",
        "system_prompt": """You are an expert academic writer specializing in literature reviews.

Write a methodological literature review that organizes research by methods and approaches.

Structure:
1. Group studies by methodological approach (e.g., experimental, observational, computational)
2. Within each method category, discuss findings and limitations
3. Compare strengths and weaknesses of different approaches
4. Identify methodological gaps or opportunities

Citation format:
- Use [Author, Year] format for citations
- Example: "Using a randomized controlled trial, Johnson [Johnson, 2019] demonstrated..."
- For multiple citations: [Smith, 2020; Jones, 2021]
- Place citations immediately after the relevant statement

Writing style:
- Academic but accessible
- Emphasize methodological details and their implications
- Critically evaluate method choices
- Synthesize findings by approach
- Target length: {target_words} words

IMPORTANT: Use ONLY the papers provided in the context. Cite sources using the [Author, Year] format provided."""
    }
}


def get_review_templates() -> List[Dict[str, str]]:
    """
    Get list of available literature review templates.

    Returns:
        List of template information dictionaries
    """
    templates = []
    for template_id, template_data in REVIEW_TEMPLATES.items():
        templates.append({
            "id": template_id,
            "name": template_data["name"],
            "description": template_data["description"]
        })
    return templates


def build_citation_map(documents: List[Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    """
    Build a map of document IDs to citation strings.

    Args:
        documents: List of document objects with analysis and citation_metadata

    Returns:
        Dictionary mapping document IDs to citation information
    """
    citation_map = {}

    for doc in documents:
        doc_id = doc.get('id')
        title = doc.get('title', 'Unknown')
        citation_meta = doc.get('analysis', {}).get('citation_metadata', {})

        first_author = citation_meta.get('first_author', 'Unknown')
        year = citation_meta.get('year', 'N/A')
        all_authors = citation_meta.get('all_authors', [])

        # Build citation string
        if len(all_authors) > 2:
            citation_str = f"{first_author} et al., {year}"
        elif len(all_authors) == 2:
            citation_str = f"{all_authors[0]} & {all_authors[1]}, {year}"
        elif len(all_authors) == 1:
            citation_str = f"{all_authors[0]}, {year}"
        else:
            citation_str = f"{first_author}, {year}"

        citation_map[doc_id] = {
            "citation": citation_str,
            "first_author": first_author,
            "year": year,
            "title": title,
            "all_authors": all_authors
        }

    return citation_map


def generate_reference_list(citation_map: Dict[str, Dict[str, str]]) -> str:
    """
    Generate a formatted reference list from citation map.

    Args:
        citation_map: Dictionary of document IDs to citation info

    Returns:
        Formatted reference list string
    """
    references = []

    # Sort by first author, then year
    sorted_citations = sorted(
        citation_map.values(),
        key=lambda x: (x['first_author'], x['year'])
    )

    for citation_info in sorted_citations:
        authors = citation_info['all_authors']
        year = citation_info['year']
        title = citation_info['title']

        if authors:
            authors_str = ', '.join(authors)
        else:
            authors_str = citation_info['first_author']

        ref = f"{authors_str} ({year}). {title}."
        references.append(ref)

    return '\n'.join(references)


def generate_literature_review(
    documents: List[Dict[str, Any]],
    structure: str = "thematic",
    theme: Optional[str] = None,
    target_words: int = 1500
) -> Dict[str, Any]:
    """
    Generate a literature review from analyzed documents.

    Args:
        documents: List of document objects with 'id', 'title', and 'analysis' fields
        structure: Review structure - "chronological", "thematic", or "methodological"
        theme: Optional specific theme to focus on
        target_words: Target word count (default: 1500)

    Returns:
        Dictionary containing:
        - review: The generated review text in markdown
        - references: Formatted reference list
        - citation_map: Mapping of citations used
        - metadata: Generation metadata
    """
    print(f"[LIT-REVIEW] Generating {structure} review from {len(documents)} documents")

    # Validate structure
    if structure not in REVIEW_TEMPLATES:
        raise ValueError(f"Invalid structure: {structure}. Must be one of {list(REVIEW_TEMPLATES.keys())}")

    # Build citation map
    citation_map = build_citation_map(documents)

    # Build context from all document analyses
    papers_context = []
    for i, doc in enumerate(documents, 1):
        doc_id = doc.get('id')
        title = doc.get('title', f'Document {i}')
        analysis = doc.get('analysis', {})
        citation_info = citation_map.get(doc_id, {})
        citation_str = citation_info.get('citation', 'Unknown, N/A')

        # Build paper summary with citation info
        paper_summary = f"""
Paper {i}: {title}
Citation: [{citation_str}]

Executive Summary:
{analysis.get('executive_summary', 'N/A')}

Research Problem:
{analysis.get('research_problem', 'N/A')}

Methodology:
- Approach: {analysis.get('methodology', {}).get('approach', 'N/A')}
- Techniques: {', '.join(analysis.get('methodology', {}).get('techniques', []))}

Key Findings:
{chr(10).join('- ' + f for f in analysis.get('key_findings', []))}

Results:
{analysis.get('results', {}).get('summary', 'N/A')}

Limitations:
{chr(10).join('- ' + l for l in analysis.get('limitations', []))}
"""
        papers_context.append(paper_summary)

    full_context = "\n\n" + "="*80 + "\n\n".join(papers_context)

    # Get template
    template = REVIEW_TEMPLATES[structure]
    system_prompt = template["system_prompt"].format(target_words=target_words)

    # Build user message
    user_message = f"""Write a literature review based on these {len(documents)} research papers.
{f"Focus specifically on: {theme}" if theme else ""}

{full_context}

Remember to:
1. Use [{citation_str}] format for ALL citations
2. Synthesize findings, don't just summarize each paper
3. Target approximately {target_words} words
4. Include a brief introduction and conclusion
5. Use only the papers provided above"""

    print(f"[LIT-REVIEW] Calling GPT-4o with {structure} template")

    # Generate review
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=2500
    )

    review_text = response.choices[0].message.content

    # Generate reference list
    references = generate_reference_list(citation_map)

    # Combine review with references
    full_review = f"""{review_text}

## References

{references}
"""

    print(f"[LIT-REVIEW] Review generated successfully")

    return {
        "review": full_review,
        "review_body": review_text,
        "references": references,
        "citation_map": citation_map,
        "metadata": {
            "structure": structure,
            "theme": theme,
            "num_documents": len(documents),
            "target_words": target_words,
            "model": "gpt-4o",
            "tokens_used": response.usage.total_tokens if response.usage else None
        }
    }
