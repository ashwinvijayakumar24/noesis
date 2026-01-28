"""
Literature Review Compass Service

Provides structural guidance for literature reviews WITHOUT auto-generating prose.

Philosophy:
- NEVER write content for the user
- Provide structure, insights, and critical questions
- Act like a senior researcher mentoring, not an AI assistant
- Help users become better writers, not replace their writing
"""

from typing import List, Dict, Any, Optional


def generate_compass_guidance(
    insights: Dict[str, Any],
    documents: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Generate Literature Review Compass guidance.

    DOES NOT GENERATE PROSE. Provides:
    - Structure recommendations with reasoning
    - Outline scaffolds (section titles + paper groupings)
    - Synthesis questions
    - Positioning prompts

    Uses ONLY existing insights data. No GPT-4o calls needed.

    Args:
        insights: Project insights analysis data
        documents: List of document metadata

    Returns:
        Dictionary containing guidance components

    Raises:
        ValueError: If inputs are invalid
    """
    # Validate inputs
    if not insights or not isinstance(insights, dict):
        raise ValueError("Invalid insights data provided")
    if not documents or len(documents) == 0:
        raise ValueError("No documents provided")

    guidance = {
        "structure_recommendations": recommend_structure(insights, documents),
        "synthesis_questions": generate_synthesis_questions(insights),
        "positioning_prompts": generate_positioning_prompts(insights),
    }

    # Validate output before returning
    validate_guidance(guidance)

    return guidance


def recommend_structure(
    insights: Dict[str, Any],
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Score and recommend review structures.

    Scoring Logic:
    - Chronological: High if timeline has 3+ periods, dates span 5+ years
    - Thematic: High if 4+ themes with balanced frequency
    - Methodological: High if 3+ distinct methods

    Returns sorted list with scores and reasoning.
    """
    recommendations = []

    # Build methodology map for methodological structure
    methods = insights.get('methodological_patterns', [])
    paper_method_map = build_paper_methodology_map(documents, methods)

    # Chronological scoring
    timeline = insights.get('timeline', [])
    pub_years = [extract_year(doc) for doc in documents if extract_year(doc)]
    year_span = max(pub_years) - min(pub_years) if len(pub_years) > 1 else 0

    chrono_score = 0.0
    chrono_reasons = []

    if len(timeline) >= 3:
        chrono_score += 0.5
        chrono_reasons.append(f"{len(timeline)} distinct time periods")
    if year_span >= 5:
        chrono_score += 0.3
        chrono_reasons.append(f"spans {year_span} years")
    if year_span >= 10:
        chrono_score += 0.2

    recommendations.append({
        "type": "chronological",
        "score": round(chrono_score, 2),
        "reasoning": f"Your literature {', '.join(chrono_reasons)}" if chrono_reasons else "Limited temporal diversity",
        "outline": generate_outline_scaffold("chronological", insights, documents, paper_method_map),
        "pros": [
            "Shows evolution of research over time",
            "Clear narrative progression",
            "Easy to identify recent trends and developments",
            "Helps readers understand historical context"
        ],
        "cons": [
            "May fragment related concepts across periods",
            "Harder to compare methodologies directly",
            "Can overemphasize recency",
            "Challenging if papers don't have clear temporal patterns"
        ]
    })

    # Thematic scoring
    themes = insights.get('common_themes', [])
    theme_score = 0.0
    theme_reasons = []

    if len(themes) >= 4:
        theme_score += 0.5
        theme_reasons.append(f"{len(themes)} major themes identified")
    if len(themes) >= 2:
        # Check balance (no single theme dominates >60%)
        max_freq = max([t.get('frequency', 0) for t in themes]) if themes else 0
        total_papers = len(documents)
        if total_papers > 0 and max_freq / total_papers < 0.6:
            theme_score += 0.4
            theme_reasons.append("balanced coverage across themes")

    recommendations.append({
        "type": "thematic",
        "score": round(theme_score, 2),
        "reasoning": f"{', '.join(theme_reasons).capitalize()}" if theme_reasons else "Limited thematic diversity",
        "outline": generate_outline_scaffold("thematic", insights, documents, paper_method_map),
        "pros": [
            "Groups related concepts together naturally",
            "Easy to compare different perspectives on same topic",
            "Flexible organization that adapts to content",
            "Highlights conceptual connections and tensions"
        ],
        "cons": [
            "May obscure temporal evolution",
            "Can be arbitrary if themes overlap significantly",
            "Requires strong conceptual clarity upfront",
            "Risk of creating artificial theme boundaries"
        ]
    })

    # Methodological scoring
    method_score = 0.0
    method_reasons = []

    if len(methods) >= 3:
        method_score += 0.6
        method_reasons.append(f"{len(methods)} distinct methodologies")
    if len(methods) >= 2:
        method_score += 0.3

    recommendations.append({
        "type": "methodological",
        "score": round(method_score, 2),
        "reasoning": f"{', '.join(method_reasons).capitalize()}" if method_reasons else "Limited methodological diversity",
        "outline": generate_outline_scaffold("methodological", insights, documents, paper_method_map),
        "pros": [
            "Highlights research approach diversity",
            "Easy to compare strengths/limitations of methods",
            "Useful for methodology-focused fields",
            "Helps identify methodological gaps"
        ],
        "cons": [
            "May fragment thematically related work",
            "Less intuitive for non-specialist readers",
            "Can be too technical and narrow",
            "Difficult if most papers use similar methods"
        ]
    })

    return sorted(recommendations, key=lambda x: x['score'], reverse=True)


def generate_outline_scaffold(
    structure: str,
    insights: Dict[str, Any],
    documents: List[Dict[str, Any]],
    paper_method_map: Optional[Dict[str, List[str]]] = None
) -> Dict[str, Any]:
    """
    Generate outline template (NO PROSE).

    Returns section titles, paper groupings, themes, synthesis prompts.

    Args:
        structure: Type of structure ("chronological", "thematic", "methodological")
        insights: Project insights data
        documents: List of document metadata
        paper_method_map: Optional mapping of methodology → paper titles

    Returns:
        Dictionary with sections list
    """
    if structure == "chronological":
        timeline = insights.get('timeline', [])
        sections = []
        for period in timeline:
            sections.append({
                "title": period.get('period', 'Unknown Period'),
                "papers": get_paper_list(period),
                "focus_themes": extract_themes_for_period(period, insights),
                "synthesis_prompt": f"What characterized {period.get('period', 'this period')}? How did methods/findings evolve?"
            })
        return {"sections": sections}

    elif structure == "thematic":
        themes = insights.get('common_themes', [])
        sections = []
        for theme in themes:
            sections.append({
                "title": theme.get('theme', 'Unknown Theme'),
                "papers": get_paper_list(theme),
                "focus_themes": [theme.get('theme', '')],
                "synthesis_prompt": f"How do findings converge on {theme.get('theme', 'this theme')}? What tensions exist?"
            })
        return {"sections": sections}

    elif structure == "methodological":
        methods = insights.get('methodological_patterns', [])
        sections = []
        for method in methods:
            method_name = method.get('methodology', 'Unknown Method')
            # Use paper_method_map if provided, otherwise empty
            papers = paper_method_map.get(method_name, []) if paper_method_map else []
            sections.append({
                "title": method_name,
                "papers": papers,
                "focus_themes": [],
                "synthesis_prompt": f"What does {method_name} reveal? What are its limitations?"
            })
        return {"sections": sections}

    return {"sections": []}


def generate_synthesis_questions(
    insights: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generate critical thinking questions from insights.

    Categories:
    - From conflicting_findings: "How do you explain X vs Y?"
    - From research_gaps: "Why hasn't Z been studied?"
    - From methodological_patterns: "What are implications?"
    - Positioning: "How does this position your research?"
    """
    questions = []

    # From conflicts
    for conflict in insights.get('conflicting_findings', []):
        topic = conflict.get('topic', 'this topic')
        side_a_papers = conflict.get('side_a', {}).get('papers', [])
        side_b_papers = conflict.get('side_b', {}).get('papers', [])
        questions.append({
            "question": f"Papers disagree on {topic}. How do you explain this divergence?",
            "category": "conflict",
            "icon": "🔄",
            "related_papers": side_a_papers + side_b_papers
        })

    # From gaps
    for gap in insights.get('research_gaps', []):
        title = gap.get('title', 'Unknown gap')
        questions.append({
            "question": f"{title}. Why might this gap be important to address?",
            "category": "gap",
            "icon": "🕳️",
            "related_papers": []
        })

    # From patterns
    for pattern in insights.get('methodological_patterns', []):
        usage_count = pattern.get('usage_count', 0)
        methodology = pattern.get('methodology', 'this methodology')
        if usage_count >= 3:
            questions.append({
                "question": f"Most papers ({usage_count}) use {methodology}. What are the implications of this consensus?",
                "category": "pattern",
                "icon": "🔬",
                "related_papers": []
            })

    # Positioning prompts
    key_insights = insights.get('key_insights', [])
    for insight in key_insights[:3]:  # Top 3
        questions.append({
            "question": f"Your literature shows: {insight}. How does this position your research contribution?",
            "category": "positioning",
            "icon": "🎯",
            "related_papers": []
        })

    return questions


def generate_positioning_prompts(
    insights: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Generate prompts to help position user's research.
    """
    prompts = []

    # From key insights
    for insight in insights.get('key_insights', [])[:5]:
        prompts.append({
            "prompt": f"Your literature shows: {insight}. How does this position your contribution?",
            "based_on": "key_insights"
        })

    # From research gaps
    research_gaps = insights.get('research_gaps', [])
    if research_gaps:
        main_gap = research_gaps[0]
        prompts.append({
            "prompt": f"The main gap is {main_gap.get('title', 'unknown')}. How does your work address this?",
            "based_on": "research_gaps"
        })

    return prompts


def extract_year(document: Dict[str, Any]) -> Optional[int]:
    """Extract publication year from document metadata."""
    try:
        # Try citation_metadata first
        citation_meta = document.get('analysis', {}).get('citation_metadata', {})
        year = citation_meta.get('year')
        if year:
            return int(year)

        # Try metadata field
        metadata = document.get('metadata', {})
        year = metadata.get('year') or metadata.get('publication_year')
        if year:
            return int(year)

        return None
    except (ValueError, TypeError):
        return None


def extract_themes_for_period(
    period: Dict[str, Any],
    insights: Dict[str, Any]
) -> List[str]:
    """Extract relevant themes for a time period."""
    period_papers = set(period.get('papers', []))
    themes = []

    for theme in insights.get('common_themes', []):
        theme_papers = set(theme.get('paper_titles', []))
        # If any papers overlap, include this theme
        if period_papers & theme_papers:
            themes.append(theme.get('theme', ''))

    return themes


def build_paper_methodology_map(
    documents: List[Dict[str, Any]],
    methodological_patterns: List[Dict[str, Any]]
) -> Dict[str, List[str]]:
    """
    Build mapping of methodology → [paper titles].

    Extracts methodology.approach from each document.analysis and matches
    against methodological_patterns to create reverse mapping.

    Args:
        documents: List of document metadata with analysis
        methodological_patterns: List of methodology patterns from insights

    Returns:
        Dictionary mapping methodology name to list of paper titles
    """
    # Initialize map
    method_map = {
        pattern.get('methodology', ''): []
        for pattern in methodological_patterns
    }

    # Map each document to methodology
    for doc in documents:
        title = doc.get('title', 'Untitled')
        analysis = doc.get('analysis', {})
        methodology = analysis.get('methodology', {})
        approach = methodology.get('approach', '').strip().lower()

        if not approach:
            continue

        # Match against patterns (fuzzy matching)
        matched = False
        for pattern in methodological_patterns:
            pattern_name = pattern.get('methodology', '').strip().lower()
            # Exact match or substring match
            if approach in pattern_name or pattern_name in approach:
                method_map[pattern.get('methodology', '')].append(title)
                matched = True
                break

    return method_map


def validate_guidance(guidance: Dict[str, Any]) -> bool:
    """
    Validate guidance structure before returning.

    Args:
        guidance: Generated guidance dictionary

    Returns:
        True if valid

    Raises:
        ValueError: If guidance structure is invalid
    """
    required_fields = ['structure_recommendations', 'synthesis_questions', 'positioning_prompts']

    for field in required_fields:
        if field not in guidance:
            raise ValueError(f"Missing required field: {field}")

    # Validate structure_recommendations
    for rec in guidance['structure_recommendations']:
        if 'type' not in rec or 'score' not in rec or 'outline' not in rec:
            raise ValueError("Invalid recommendation structure - missing required fields")
        if not isinstance(rec['score'], (int, float)) or rec['score'] < 0 or rec['score'] > 1:
            raise ValueError(f"Invalid recommendation score: {rec['score']} (must be between 0 and 1)")

    # Validate synthesis_questions
    for q in guidance['synthesis_questions']:
        if 'question' not in q or 'category' not in q:
            raise ValueError("Invalid question structure - missing required fields")

    return True


def get_paper_list(data: Dict[str, Any]) -> List[str]:
    """
    Get paper list with backward compatibility for old field names.

    Args:
        data: Dictionary that might contain papers under different field names

    Returns:
        List of paper titles/references
    """
    return (
        data.get('paper_titles') or
        data.get('papers') or
        data.get('papers_citing') or
        []
    )
