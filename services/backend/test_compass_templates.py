"""
Quick test for Template Library functionality
"""

from app.services.literature_compass import TemplateLibrary, calculate_position_diversity

# Test 1: Template selection prioritizes conditions
print("Test 1: Template Selection")
print("-" * 50)

# Context with high gap count (should trigger gap_focused template)
context_gap = {
    "gap_count": 5,
    "primary_gap_category": "methodological",
    "primary_gap_title": "lack of longitudinal studies",
    "document_count": 10,
    "conflict_count": 1,
    "pattern_count": 2
}

template = TemplateLibrary.select_template(
    TemplateLibrary.STRUCTURE_TEMPLATES,
    context_gap
)

print(f"Context: {context_gap}")
print(f"Selected Template ID: {template['id']}")
print(f"Expected: gap_focused")
print(f"✓ PASS" if template['id'] == 'gap_focused' else "✗ FAIL")
print()

# Test 2: Template variation with used_template_ids
print("Test 2: Template Variation")
print("-" * 50)

used_ids = {'gap_focused'}
template2 = TemplateLibrary.select_template(
    TemplateLibrary.STRUCTURE_TEMPLATES,
    context_gap,
    used_template_ids=used_ids
)

print(f"Used Template IDs: {used_ids}")
print(f"Selected Template ID: {template2['id']}")
print(f"Expected: NOT gap_focused (should be different)")
print(f"✓ PASS" if template2['id'] != 'gap_focused' else "✗ FAIL")
print()

# Test 3: Context building from conflict
print("Test 3: Context Building from Conflict")
print("-" * 50)

conflict_data = {
    "topic": "effectiveness of X vs Y",
    "side_a": {
        "position": "X is more effective",
        "papers": ["Paper A", "Paper B"],
        "evidence": "Studies show X has 20% better outcomes"
    },
    "side_b": {
        "position": "Y is more effective",
        "papers": ["Paper C", "Paper D"],
        "evidence": "Y has lower cost and comparable efficacy"
    },
    "resolution": "Context matters: X for acute cases, Y for chronic"
}

insights = {
    "conflicting_findings": [conflict_data],
    "research_gaps": [],
    "methodological_patterns": [],
    "common_themes": []
}

context = TemplateLibrary.build_context(
    insights=insights,
    documents=[{"title": "Paper A"}] * 10,
    conflict=conflict_data
)

print(f"Context keys: {list(context.keys())}")
print(f"Source type: {context.get('source_type')}")
print(f"Topic: {context.get('topic')}")
print(f"Side A position: {context.get('side_a_position')}")
print(f"Has resolution: {context.get('has_resolution')}")
print(f"Position diversity: {context.get('position_diversity')}")
print(f"✓ PASS" if context.get('source_type') == 'conflict' else "✗ FAIL")
print()

# Test 4: Calculate position diversity
print("Test 4: Position Diversity Calculation")
print("-" * 50)

diversity = calculate_position_diversity(conflict_data)
print(f"Conflict data: {conflict_data}")
print(f"Position diversity score: {diversity}")
print(f"Expected: 1.0 (all fields present)")
print(f"✓ PASS" if diversity == 1.0 else "✗ FAIL")
print()

# Test 5: Template population
print("Test 5: Template Population")
print("-" * 50)

template_str = "Your literature reveals {gap_count} gaps in {primary_gap_category}. Focus on {primary_gap_title}."
populated = TemplateLibrary.populate_template(template_str, context_gap)
print(f"Template: {template_str}")
print(f"Populated: {populated}")
print(f"✓ PASS" if "5 gaps" in populated and "methodological" in populated else "✗ FAIL")
print()

# Test 6: Question confidence calculation
print("Test 6: Question Confidence Calculation")
print("-" * 50)

context_with_resolution = {
    "has_resolution": True,
    "gap_description": "detailed description",
    "usage_count": 5,
    "position_diversity": 0.8
}

confidence = TemplateLibrary.calculate_question_confidence(
    context_with_resolution,
    template
)
print(f"Context: {context_with_resolution}")
print(f"Confidence score: {confidence}")
print(f"Expected: > 0.8 (rich data)")
print(f"✓ PASS" if confidence > 0.8 else "✗ FAIL")
print()

print("=" * 50)
print("All tests completed!")
print("=" * 50)
