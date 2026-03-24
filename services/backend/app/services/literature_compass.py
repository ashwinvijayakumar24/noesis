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
import random


class TemplateLibrary:
    """
    Manages template variations for structure guidance and synthesis questions.
    Provides context-aware selection to prevent repetitive wording.
    """

    # Structure Guidance Templates with conditions
    STRUCTURE_TEMPLATES = [
        {
            "id": "gap_focused",
            "priority": 10,
            "condition": lambda ctx: ctx.get("gap_count", 0) >= 3,
            "template": "Your literature reveals {gap_count} significant research gaps, particularly in {primary_gap_category}. Consider organizing your review to systematically expose these gaps, building a case for why {primary_gap_title} deserves attention. Structure sections to progressively narrow from broad landscape to specific gap.",
        },
        {
            "id": "conflict_driven",
            "priority": 9,
            "condition": lambda ctx: ctx.get("conflict_count", 0) >= 2 and ctx.get("position_diversity", 0) > 0.6,
            "template": "Multiple conflicting perspectives exist on {primary_conflict_topic}, with {conflict_count} distinct debates. A dialectical structure could work well: present each position's evidence (side A: {side_a_position}; side B: {side_b_position}), analyze strengths/weaknesses, then synthesize. {resolution_hint}",
        },
        {
            "id": "pattern_based",
            "priority": 8,
            "condition": lambda ctx: ctx.get("pattern_strength", 0) > 0.7 and ctx.get("usage_count", 0) >= 4,
            "template": "Methodological consensus emerged: {primary_methodology} dominates ({usage_count} papers). This pattern suggests organizing by methodological tradition—comparing what each approach reveals and obscures. {pattern_variations_hint}",
        },
        {
            "id": "methodology_focused",
            "priority": 7,
            "condition": lambda ctx: ctx.get("method_diversity", 0) >= 3,
            "template": "Your literature employs {method_diversity} distinct research methods. A methods-based structure would clarify each approach's contributions and limitations. Consider: how do findings from {method_1} compare with those from {method_2}? What becomes visible through methodological pluralism?",
        },
        {
            "id": "default",
            "priority": 1,
            "condition": lambda ctx: True,  # Always matches
            "template": "Your literature collection shows diverse characteristics. Consider how best to organize these {document_count} papers: by theme (highlighting conceptual connections), chronology (showing evolution), or methodology (comparing approaches). Each structure foregrounds different insights.",
        },
    ]

    # Synthesis Question Templates with conditions
    SYNTHESIS_TEMPLATES = [
        {
            "id": "conflict_resolution",
            "priority": 10,
            "condition": lambda ctx: "conflict" in ctx.get("source_type", "") and ctx.get("has_resolution", False),
            "template": "Papers diverge on {topic}: {side_a_position} versus {side_b_position}. Given that {side_a_evidence}, but also {side_b_evidence}, {resolution}. How would you defend one position over the other, or propose a synthesis?",
            "difficulty": "high",
            "category": "conflict",
        },
        {
            "id": "gap_bridging",
            "priority": 9,
            "condition": lambda ctx: "gap" in ctx.get("source_type", ""),
            "template": "{gap_description}. None of the {document_count} papers address this directly. Why might researchers have avoided this question? What methodological or theoretical barriers exist? {suggested_directions_hint}",
            "difficulty": "medium",
            "category": "gap",
        },
        {
            "id": "pattern_extension",
            "priority": 8,
            "condition": lambda ctx: "pattern" in ctx.get("source_type", "") and ctx.get("has_variations", False),
            "template": "{usage_count} papers converge on {methodology}, though {variations_hint}. What assumptions underlie this methodological consensus? What alternative approaches might challenge or complement these findings?",
            "difficulty": "medium",
            "category": "pattern",
        },
        {
            "id": "methodological_synthesis",
            "priority": 7,
            "condition": lambda ctx: ctx.get("method_diversity", 0) >= 2,
            "template": "Comparing {method_1} (used by {method_1_count} papers) with {method_2} (used by {method_2_count} papers): What does each methodology reveal that the other obscures? How might combining these approaches generate novel insights?",
            "difficulty": "high",
            "category": "methodology",
        },
        {
            "id": "temporal_evolution",
            "priority": 6,
            "condition": lambda ctx: ctx.get("year_span", 0) >= 5,
            "template": "From {earliest_year} to {latest_year}, how has understanding of {theme} evolved? What earlier assumptions have been challenged? What continuities persist despite {year_span} years of research?",
            "difficulty": "medium",
            "category": "temporal",
        },
        {
            "id": "cross_domain",
            "priority": 5,
            "condition": lambda ctx: len(ctx.get("domains", [])) >= 2,
            "template": "Your literature spans {domain_count} domains: {domains_list}. How do insights from {domain_1} inform or challenge assumptions in {domain_2}? What interdisciplinary connections remain unexplored?",
            "difficulty": "high",
            "category": "cross_domain",
        },
        {
            "id": "evidence_weighting",
            "priority": 4,
            "condition": lambda ctx: ctx.get("evidence_variance", 0) > 0.5,
            "template": "Evidence quality varies significantly across papers. Which studies provide the strongest empirical foundation for {claim}? How do you weigh {strong_evidence_type} against {weak_evidence_type}?",
            "difficulty": "medium",
            "category": "evidence",
        },
        {
            "id": "generative",
            "priority": 3,
            "condition": lambda ctx: bool(ctx.get("insight")),
            "template": "Reflecting on {insight}: How does this pattern position your research contribution? What aspects of the existing literature does your work extend, challenge, or synthesize?",
            "difficulty": "low",
            "category": "positioning",
        },
    ]

    @classmethod
    def select_template(
        cls,
        templates: List[Dict[str, Any]],
        context: Dict[str, Any],
        used_template_ids: set = None
    ) -> Optional[Dict[str, Any]]:
        """
        Select the highest-priority template matching the current context.
        Avoids recently used templates to ensure variation.

        Args:
            templates: List of template dictionaries
            context: Current context data for condition evaluation
            used_template_ids: Set of template IDs already used (to avoid repetition)

        Returns:
            Selected template dictionary or None
        """
        if used_template_ids is None:
            used_template_ids = set()

        # Filter templates that match conditions and haven't been used
        matching_templates = [
            t for t in templates
            if t["condition"](context) and t["id"] not in used_template_ids
        ]

        # If all templates used, allow reuse with randomization (no re-sort — that kills variation)
        if not matching_templates:
            matching_templates = [t for t in templates if t["condition"](context)]
            if matching_templates:
                random.shuffle(matching_templates)
            return matching_templates[0] if matching_templates else None

        # Sort by priority (highest first) — only for the primary (non-fallback) path
        matching_templates.sort(key=lambda t: t["priority"], reverse=True)

        return matching_templates[0] if matching_templates else None

    @classmethod
    def build_context(
        cls,
        insights: Dict[str, Any],
        documents: List[Dict[str, Any]],
        conflict: Optional[Dict[str, Any]] = None,
        gap: Optional[Dict[str, Any]] = None,
        pattern: Optional[Dict[str, Any]] = None,
        theme: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Build context dictionary from insights data for template selection.

        Args:
            insights: Project insights data
            documents: List of document metadata
            conflict: Optional conflict data
            gap: Optional gap data
            pattern: Optional pattern data
            theme: Optional theme data

        Returns:
            Context dictionary with all available variables
        """
        context = {
            "document_count": len(documents),
            "gap_count": len(insights.get("research_gaps", [])),
            "conflict_count": len(insights.get("conflicting_findings", [])),
            "pattern_count": len(insights.get("methodological_patterns", [])),
            "theme_count": len(insights.get("common_themes", [])),
        }

        # Add conflict-specific context
        if conflict:
            context["source_type"] = "conflict"
            context["topic"] = conflict.get("topic", "this topic")
            side_a = conflict.get("side_a", {})
            side_b = conflict.get("side_b", {})
            context["side_a_position"] = side_a.get("position", "unknown position")
            context["side_b_position"] = side_b.get("position", "unknown position")
            context["side_a_evidence"] = side_a.get("evidence", "")
            context["side_b_evidence"] = side_b.get("evidence", "")
            context["has_resolution"] = bool(conflict.get("resolution"))
            context["resolution"] = conflict.get("resolution", "")
            context["position_diversity"] = calculate_position_diversity(conflict)

            # Determine primary conflict
            context["primary_conflict_topic"] = conflict.get("topic", "unknown")

        # Add gap-specific context
        if gap:
            context["source_type"] = "gap"
            context["gap_description"] = gap.get("description", gap.get("title", ""))
            context["primary_gap_title"] = gap.get("title", "unknown gap")
            context["primary_gap_category"] = gap.get("category", "this area")
            context["suggested_directions_hint"] = (
                f"Suggested directions: {', '.join(gap.get('suggested_directions', [])[:2])}"
                if gap.get("suggested_directions") else ""
            )

        # Add pattern-specific context
        if pattern:
            context["source_type"] = "pattern"
            context["methodology"] = pattern.get("methodology", "this methodology")
            context["primary_methodology"] = pattern.get("methodology", "unknown method")
            context["usage_count"] = pattern.get("usage_count", 0)
            context["has_variations"] = bool(pattern.get("variations"))
            context["variations_hint"] = (
                f"with variations like {', '.join(pattern.get('variations', [])[:2])}"
                if pattern.get("variations") else "with subtle variations"
            )
            context["pattern_description"] = pattern.get("description", "")
            context["pattern_strength"] = min(1.0, pattern.get("usage_count", 0) / max(len(documents), 1))

        # Add theme-specific context
        if theme:
            context["theme"] = theme.get("theme", "this theme")
            context["insight"] = theme.get("description", theme.get("theme", ""))

        # Add method diversity
        methods = insights.get("methodological_patterns", [])
        context["method_diversity"] = len(methods)
        if len(methods) >= 2:
            context["method_1"] = methods[0].get("methodology", "method A")
            context["method_2"] = methods[1].get("methodology", "method B")
            context["method_1_count"] = methods[0].get("usage_count", 0)
            context["method_2_count"] = methods[1].get("usage_count", 0)

        # Add temporal context
        pub_years = [extract_year(doc) for doc in documents if extract_year(doc)]
        if pub_years:
            context["earliest_year"] = min(pub_years)
            context["latest_year"] = max(pub_years)
            context["year_span"] = max(pub_years) - min(pub_years)

        # Add domain context (placeholder - would need domain extraction)
        context["domains"] = []
        context["domain_count"] = 0

        # Evidence variance (placeholder - would need actual calculation)
        context["evidence_variance"] = 0.5

        return context

    @classmethod
    def populate_template(cls, template_str: str, context: Dict[str, Any]) -> str:
        """
        Fill template variables with actual data from context.

        Args:
            template_str: Template string with {variable} placeholders
            context: Context dictionary with variable values

        Returns:
            Populated template string
        """
        try:
            return template_str.format(**context)
        except KeyError as e:
            # If a variable is missing, use empty string or fallback
            import re
            # Replace any unmatched {variable} with empty string
            result = template_str
            for match in re.findall(r'\{(\w+)\}', template_str):
                if match not in context:
                    result = result.replace(f'{{{match}}}', f'[{match}]')
            return result

    @classmethod
    def extract_source_ids(
        cls,
        conflict: Optional[Dict[str, Any]] = None,
        gap: Optional[Dict[str, Any]] = None,
        pattern: Optional[Dict[str, Any]] = None
    ) -> Dict[str, List[str]]:
        """
        Extract source IDs from conflicts/gaps/patterns for cross-linking.

        Returns:
            Dictionary with source_conflicts, source_gaps, source_patterns lists
        """
        sources = {
            "source_conflicts": [],
            "source_gaps": [],
            "source_patterns": []
        }

        if conflict:
            topic = conflict.get("topic", "")
            if topic:
                sources["source_conflicts"].append(topic)

        if gap:
            title = gap.get("title", "")
            if title:
                sources["source_gaps"].append(title)

        if pattern:
            methodology = pattern.get("methodology", "")
            if methodology:
                sources["source_patterns"].append(methodology)

        return sources

    @classmethod
    def calculate_question_confidence(
        cls,
        context: Dict[str, Any],
        template: Dict[str, Any]
    ) -> float:
        """
        Calculate confidence score (0-1) for a question based on data richness.

        Args:
            context: Context data
            template: Template used

        Returns:
            Confidence score between 0 and 1
        """
        score = 0.5  # Base score

        # Increase confidence if we have rich data
        if context.get("has_resolution"):
            score += 0.15
        if context.get("gap_description"):
            score += 0.10
        if context.get("pattern_description"):
            score += 0.10
        if context.get("usage_count", 0) >= 3:
            score += 0.10
        if context.get("position_diversity", 0) > 0.6:
            score += 0.15

        return min(1.0, score)


def calculate_position_diversity(conflict: Dict[str, Any]) -> float:
    """
    Calculate diversity score for conflict positions (0-1).

    Args:
        conflict: Conflict data with side_a and side_b

    Returns:
        Diversity score between 0 and 1
    """
    side_a = conflict.get("side_a", {})
    side_b = conflict.get("side_b", {})

    # Simple heuristic: if both sides have evidence and papers, diversity is high
    has_a_evidence = bool(side_a.get("evidence"))
    has_b_evidence = bool(side_b.get("evidence"))
    has_a_papers = len(side_a.get("papers", [])) > 0
    has_b_papers = len(side_b.get("papers", [])) > 0

    score = 0.0
    if has_a_evidence:
        score += 0.25
    if has_b_evidence:
        score += 0.25
    if has_a_papers:
        score += 0.25
    if has_b_papers:
        score += 0.25

    return score


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

    Uses ONLY existing insights data. No GPT-5.2 calls needed.

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
        "synthesis_questions": generate_synthesis_questions(insights, documents),
        "positioning_prompts": generate_positioning_prompts(insights),
        "structure_guidance": _generate_structure_guidance(insights, documents),
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
    insights: Dict[str, Any],
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate critical thinking questions from insights using template library.

    Now with rich metadata and template variation to prevent repetition!

    Categories:
    - From conflicting_findings: Multiple conflict resolution templates
    - From research_gaps: Gap bridging and importance templates
    - From methodological_patterns: Pattern analysis templates
    - Positioning: Research positioning templates

    Returns:
        List of question dictionaries with metadata (confidence, difficulty, sources)
    """
    questions = []
    seen_questions: set = set()  # Global dedup on final question text

    # From conflicts — each loop gets its own fresh used_template_ids
    for conflict in insights.get('conflicting_findings', []):
        loop_used: set = set()
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            conflict=conflict
        )

        template = TemplateLibrary.select_template(
            TemplateLibrary.SYNTHESIS_TEMPLATES,
            context,
            loop_used
        )

        if template:
            loop_used.add(template["id"])
            question_text = TemplateLibrary.populate_template(template["template"], context)
            if question_text in seen_questions:
                continue
            seen_questions.add(question_text)
            sources = TemplateLibrary.extract_source_ids(conflict=conflict)
            confidence = TemplateLibrary.calculate_question_confidence(context, template)

            side_a_papers = conflict.get('side_a', {}).get('papers', [])
            side_b_papers = conflict.get('side_b', {}).get('papers', [])

            questions.append({
                "question": question_text,
                "category": template.get("category", "conflict"),
                "icon": "🔄",
                "related_papers": side_a_papers + side_b_papers,
                "difficulty": template.get("difficulty", "medium"),
                "confidence": round(confidence, 2),
                "metadata": sources,
                "actionable": True
            })

    # From gaps
    for gap in insights.get('research_gaps', []):
        loop_used = set()
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            gap=gap
        )

        template = TemplateLibrary.select_template(
            TemplateLibrary.SYNTHESIS_TEMPLATES,
            context,
            loop_used
        )

        if template:
            loop_used.add(template["id"])
            question_text = TemplateLibrary.populate_template(template["template"], context)
            if question_text in seen_questions:
                continue
            seen_questions.add(question_text)
            sources = TemplateLibrary.extract_source_ids(gap=gap)
            confidence = TemplateLibrary.calculate_question_confidence(context, template)

            questions.append({
                "question": question_text,
                "category": template.get("category", "gap"),
                "icon": "🕳️",
                "related_papers": [],
                "difficulty": template.get("difficulty", "medium"),
                "confidence": round(confidence, 2),
                "metadata": sources,
                "actionable": True,
                "requirements": gap.get("suggested_directions", [])
            })

    # From patterns (only if usage >= 3)
    for pattern in insights.get('methodological_patterns', []):
        usage_count = pattern.get('usage_count', 0)
        if usage_count < 3:
            continue

        loop_used = set()
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            pattern=pattern
        )

        template = TemplateLibrary.select_template(
            TemplateLibrary.SYNTHESIS_TEMPLATES,
            context,
            loop_used
        )

        if template:
            loop_used.add(template["id"])
            question_text = TemplateLibrary.populate_template(template["template"], context)
            if question_text in seen_questions:
                continue
            seen_questions.add(question_text)
            sources = TemplateLibrary.extract_source_ids(pattern=pattern)
            confidence = TemplateLibrary.calculate_question_confidence(context, template)

            questions.append({
                "question": question_text,
                "category": template.get("category", "pattern"),
                "icon": "🔬",
                "related_papers": [],
                "difficulty": template.get("difficulty", "medium"),
                "confidence": round(confidence, 2),
                "metadata": sources,
                "actionable": True
            })

    # Positioning prompts from key insights (limit to top 5)
    key_insights = insights.get('key_insights', [])
    for insight in key_insights[:5]:
        loop_used = set()
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            theme={"theme": "key insight", "description": insight}
        )

        template = TemplateLibrary.select_template(
            TemplateLibrary.SYNTHESIS_TEMPLATES,
            context,
            loop_used
        )

        if template:
            loop_used.add(template["id"])
            question_text = TemplateLibrary.populate_template(template["template"], context)
            if question_text in seen_questions:
                continue
            seen_questions.add(question_text)
            confidence = TemplateLibrary.calculate_question_confidence(context, template)

            questions.append({
                "question": question_text,
                "category": "positioning",
                "icon": "🎯",
                "related_papers": [],
                "difficulty": "low",
                "confidence": round(confidence, 2),
                "metadata": {
                    "source_conflicts": [],
                    "source_gaps": [],
                    "source_patterns": []
                },
                "actionable": True
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


def _generate_structure_guidance(
    insights: Dict[str, Any],
    documents: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Generate structure guidance using template library to avoid repetition.

    Returns:
        List of guidance dictionaries with text, type, priority, source_data
    """
    guidance_items = []
    used_template_ids = set()

    # Collect all potential sources for guidance
    conflicts = insights.get('conflicting_findings', [])
    gaps = insights.get('research_gaps', [])
    patterns = insights.get('methodological_patterns', [])

    # Prioritize by count and strength
    sources = []

    # Add gap-focused guidance (high priority if 3+ gaps)
    for gap in gaps[:3]:  # Top 3 gaps
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            gap=gap
        )
        sources.append({
            "type": "gap",
            "priority": 3 if len(gaps) >= 3 else 2,
            "context": context,
            "data": gap
        })

    # Add conflict-driven guidance (high priority if strong conflicts)
    for conflict in conflicts[:3]:  # Top 3 conflicts
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            conflict=conflict
        )
        sources.append({
            "type": "conflict",
            "priority": 3 if context.get("position_diversity", 0) > 0.6 else 2,
            "context": context,
            "data": conflict
        })

    # Add pattern-based guidance (high priority if strong patterns)
    for pattern in patterns[:3]:  # Top 3 patterns
        if pattern.get('usage_count', 0) < 3:
            continue
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents,
            pattern=pattern
        )
        sources.append({
            "type": "pattern",
            "priority": 3 if pattern.get('usage_count', 0) >= 4 else 2,
            "context": context,
            "data": pattern
        })

    # Sort sources by priority (highest first)
    sources.sort(key=lambda s: s["priority"], reverse=True)

    # Generate guidance from top sources (max 5 items)
    for source in sources[:5]:
        template = TemplateLibrary.select_template(
            TemplateLibrary.STRUCTURE_TEMPLATES,
            source["context"],
            used_template_ids
        )

        if template:
            used_template_ids.add(template["id"])
            guidance_text = TemplateLibrary.populate_template(
                template["template"],
                source["context"]
            )

            # Extract source data for cross-linking
            source_data = {}
            if source["type"] == "conflict":
                source_data = {
                    "conflicts": [source["data"].get("topic", "")],
                    "gaps": [],
                    "patterns": []
                }
            elif source["type"] == "gap":
                source_data = {
                    "conflicts": [],
                    "gaps": [source["data"].get("title", "")],
                    "patterns": []
                }
            elif source["type"] == "pattern":
                source_data = {
                    "conflicts": [],
                    "gaps": [],
                    "patterns": [source["data"].get("methodology", "")]
                }

            guidance_items.append({
                "text": guidance_text,
                "type": source["type"],
                "priority": source["priority"],
                "source_data": source_data
            })

    # If no specific guidance generated, add default
    if not guidance_items:
        context = TemplateLibrary.build_context(
            insights=insights,
            documents=documents
        )
        template = TemplateLibrary.select_template(
            TemplateLibrary.STRUCTURE_TEMPLATES,
            context,
            used_template_ids
        )
        if template:
            guidance_text = TemplateLibrary.populate_template(
                template["template"],
                context
            )
            guidance_items.append({
                "text": guidance_text,
                "type": "general",
                "priority": 1,
                "source_data": {
                    "conflicts": [],
                    "gaps": [],
                    "patterns": []
                }
            })

    return guidance_items


def extract_year(document: Dict[str, Any]) -> Optional[int]:
    """Extract publication year from document metadata."""
    try:
        # Try citation_metadata first
        analysis = document.get('analysis') or {}
        citation_meta = analysis.get('citation_metadata') or {}
        year = citation_meta.get('year')
        if year:
            return int(year)

        # Try metadata field
        metadata = document.get('metadata') or {}
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
        analysis = doc.get('analysis') or {}
        methodology = analysis.get('methodology') or {}
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
    required_fields = ['structure_recommendations', 'synthesis_questions', 'positioning_prompts', 'structure_guidance']

    for field in required_fields:
        if field not in guidance:
            raise ValueError(f"Missing required field: {field}")

    # Validate structure_recommendations
    for rec in guidance['structure_recommendations']:
        if 'type' not in rec or 'score' not in rec or 'outline' not in rec:
            raise ValueError("Invalid recommendation structure - missing required fields")
        if not isinstance(rec['score'], (int, float)) or rec['score'] < 0 or rec['score'] > 1:
            raise ValueError(f"Invalid recommendation score: {rec['score']} (must be between 0 and 1)")

    # Validate synthesis_questions (now with rich metadata)
    for q in guidance['synthesis_questions']:
        if 'question' not in q or 'category' not in q:
            raise ValueError("Invalid question structure - missing required fields")
        # Validate new metadata fields
        if 'confidence' in q and not isinstance(q['confidence'], (int, float)):
            raise ValueError(f"Invalid confidence score: {q['confidence']}")
        if 'difficulty' in q and q['difficulty'] not in ['low', 'medium', 'high']:
            raise ValueError(f"Invalid difficulty level: {q['difficulty']}")

    # Validate structure_guidance (new field)
    for item in guidance['structure_guidance']:
        if 'text' not in item or 'type' not in item:
            raise ValueError("Invalid guidance structure - missing required fields")

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
