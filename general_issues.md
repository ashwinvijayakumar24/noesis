6. Concrete Product Fixes Ranked by Impact
Fuzzy Deduplication (Critical): Your deduplication logic relies too heavily on the Type and Issue family tags. Implement a semantic similarity threshold (e.g., if the extracted Text/Anchor overlaps by >80%, force a merge regardless of what "type" the sub-agent labeled it).

Sanitize Anchors (High): Add a regex or post-processing filter to strip out prefixes like "Claim in Abstract:" or "— no supporting citations found." from the anchor fields. Anchors must be strict substrings of the source text.

Merge RAG Payloads (High): When tasks are merged (like the 13 duplicates in Task 1), ensure the Suggested sources arrays are concatenated and deduplicated so the final canonical task doesn't lose the retrieved papers.

Calibrate Readiness Deductions (Medium): Adjust the total_deductions weighting. A missing citation should cost 1-2 points, not trigger a massive penalty that drops the paper to a 42/100.