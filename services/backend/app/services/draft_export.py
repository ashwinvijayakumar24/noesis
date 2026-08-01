"""
Draft Analysis Export Service

Enables users to export draft analysis results in various formats for integration
with their writing workflow.

Supported formats:
- PDF (formatted report for sharing with advisors)

Requirements: 8.1, 8.2, Export Features - Draft PDF export
"""

from datetime import datetime as dt
from typing import Dict, Any
from app.core.logging_config import get_logger
from weasyprint import HTML
import html as html_module

logger = get_logger(__name__)


# ============================================
# Export Orchestration
# ============================================


def export_draft_analysis_as_pdf(
    draft_id: str,
    draft_title: str,
    analysis_data: Dict[str, Any]
) -> bytes:
    """
    Export draft analysis as a formatted PDF report.

    Args:
        draft_id: Draft ID
        draft_title: Draft title
        analysis_data: Combined analysis data including claims, gaps, feedback

    Returns:
        PDF file as bytes

    Requirements: Export Features - Draft Analysis PDF export
    """
    # Extract data sections
    draft_analysis = analysis_data.get("draft_analysis", {})
    claims = analysis_data.get("claims", [])
    gaps = analysis_data.get("coverage_gaps", [])
    feedback = analysis_data.get("reviewer_feedback", [])
    citation_suggestions = analysis_data.get("citation_suggestions", [])

    # Build HTML content with comprehensive styling
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Draft Analysis - {html_module.escape(draft_title)}</title>
        <style>
            @page {{
                size: A4;
                margin: 2.5cm;
                @bottom-right {{
                    content: "Page " counter(page);
                    font-size: 10pt;
                    color: #666;
                }}
            }}

            body {{
                font-family: Georgia, serif;
                font-size: 11pt;
                line-height: 1.6;
                color: #1a1a1a;
            }}

            h1 {{
                font-size: 24pt;
                font-weight: bold;
                color: #2563eb;
                border-bottom: 3px solid #2563eb;
                padding-bottom: 10px;
                margin-bottom: 30px;
            }}

            h2 {{
                font-size: 18pt;
                font-weight: bold;
                color: #1e40af;
                margin-top: 30px;
                margin-bottom: 15px;
                page-break-after: avoid;
            }}

            h3 {{
                font-size: 14pt;
                font-weight: bold;
                color: #3b82f6;
                margin-top: 20px;
                margin-bottom: 10px;
            }}

            .metadata {{
                background: #f3f4f6;
                border-left: 4px solid #6366f1;
                padding: 15px;
                margin-bottom: 30px;
                font-size: 10pt;
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 15px;
                margin: 20px 0;
            }}

            .stat-box {{
                text-align: center;
                padding: 15px;
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
            }}

            .stat-number {{
                font-size: 28pt;
                font-weight: bold;
                color: #2563eb;
            }}

            .stat-label {{
                font-size: 9pt;
                color: #6b7280;
                text-transform: uppercase;
            }}

            .claim {{
                border: 1px solid #d1d5db;
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 15px;
                page-break-inside: avoid;
            }}

            .claim-missing {{
                border-left: 4px solid #ef4444;
                background: #fef2f2;
            }}

            .claim-cited {{
                border-left: 4px solid #3b82f6;
                background: #eff6ff;
            }}

            .claim-original {{
                border-left: 4px solid #10b981;
                background: #f0fdf4;
            }}

            .feedback {{
                border: 1px solid #e5e7eb;
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 12px;
                page-break-inside: avoid;
            }}

            .feedback-error {{
                border-left: 4px solid #dc2626;
                background: #fef2f2;
            }}

            .feedback-warning {{
                border-left: 4px solid #f59e0b;
                background: #fffbeb;
            }}

            .feedback-suggestion {{
                border-left: 4px solid #3b82f6;
                background: #eff6ff;
            }}

            .gap {{
                border: 1px solid #e5e7eb;
                border-left: 4px solid #8b5cf6;
                border-radius: 6px;
                padding: 12px;
                margin-bottom: 12px;
                background: #faf5ff;
                page-break-inside: avoid;
            }}

            .tag {{
                display: inline-block;
                background: #dbeafe;
                color: #1e40af;
                padding: 2px 8px;
                border-radius: 12px;
                font-size: 9pt;
                font-weight: 600;
                margin-right: 5px;
            }}

            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 1px solid #e5e7eb;
                font-size: 9pt;
                color: #9ca3af;
                text-align: center;
            }}
        </style>
    </head>
    <body>
        <h1>Draft Analysis Report</h1>

        <div class="metadata">
            <strong>Document:</strong> {html_module.escape(draft_title)}<br>
            <strong>Generated:</strong> {dt.now().strftime('%B %d, %Y at %H:%M')}<br>
            <strong>Word Count:</strong> {draft_analysis.get('word_count', 'N/A')}<br>
            <strong>Draft ID:</strong> {draft_id}
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-number">{len(claims)}</div>
                <div class="stat-label">Claims</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(gaps)}</div>
                <div class="stat-label">Coverage Gaps</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(feedback)}</div>
                <div class="stat-label">Feedback Items</div>
            </div>
            <div class="stat-box">
                <div class="stat-number">{len(citation_suggestions)}</div>
                <div class="stat-label">Citation Suggestions</div>
            </div>
        </div>
    """

    # Add Claims section
    if claims:
        html_content += """
        <h2 style="page-break-before: auto;">1. Extracted Claims</h2>
        <p>AI-identified claims in your draft that may require supporting citations.</p>
        """

        for claim in sorted(claims, key=lambda x: x.get('importance_score', 0), reverse=True):
            has_citations = claim.get('existing_citations') and len(claim.get('existing_citations', [])) > 0
            requires_citation = claim.get('requires_citation', True)

            css_class = 'claim '
            if not requires_citation:
                css_class += 'claim-original'
                status = '✓ ORIGINAL'
            elif has_citations:
                css_class += 'claim-cited'
                status = '✓ CITED'
            else:
                css_class += 'claim-missing'
                status = '⚠ NEEDS CITATIONS'

            claim_text = html_module.escape(claim.get('claim_text', ''))
            claim_type = html_module.escape(claim.get('claim_type', 'empirical'))
            section = html_module.escape(claim.get('section_location', 'Unknown'))
            importance = claim.get('importance_score', 0) * 100

            html_content += f"""
            <div class="{css_class}">
                <div style="margin-bottom: 8px;">
                    <span class="tag">{claim_type.upper()}</span>
                    <span class="tag">{section}</span>
                    <span class="tag">Importance: {importance:.0f}%</span>
                    <span class="tag">{status}</span>
                </div>
                <p style="margin: 8px 0; font-weight: 500;">{claim_text}</p>
            """

            if has_citations:
                citations = ', '.join(html_module.escape(str(c)) for c in claim.get('existing_citations', []))
                html_content += f'<p style="font-size: 9pt; color: #4b5563; margin-top: 5px;"><strong>Citations:</strong> {citations}</p>'

            html_content += "</div>"

    # Add Coverage Gaps section
    if gaps:
        html_content += """
        <h2 style="page-break-before: always;">2. Coverage Gaps</h2>
        <p>Areas where additional literature may strengthen your argument.</p>
        """

        for gap in sorted(gaps, key=lambda x: x.get('priority', 0), reverse=True):
            gap_type = html_module.escape(gap.get('gap_type', 'unknown'))
            description = html_module.escape(gap.get('description', ''))
            priority = html_module.escape(gap.get('priority', 'medium'))

            html_content += f"""
            <div class="gap">
                <div style="margin-bottom: 8px;">
                    <span class="tag">{gap_type.upper()}</span>
                    <span class="tag">PRIORITY: {priority.upper()}</span>
                </div>
                <p style="margin: 0;">{description}</p>
            </div>
            """

    # Add Reviewer Feedback section
    if feedback:
        html_content += """
        <h2 style="page-break-before: always;">3. Expert Reviewer Feedback</h2>
        <p>Academic reviewer-style feedback on your draft.</p>
        """

        # Group by severity
        errors = [f for f in feedback if f.get('severity') == 'error']
        warnings = [f for f in feedback if f.get('severity') == 'warning']
        suggestions = [f for f in feedback if f.get('severity') == 'suggestion']

        for severity_group, items in [('Errors', errors), ('Warnings', warnings), ('Suggestions', suggestions)]:
            if items:
                html_content += f"<h3>{severity_group} ({len(items)})</h3>"

                for item in items:
                    feedback_type = html_module.escape(item.get('feedback_type', 'general'))
                    feedback_text = html_module.escape(item.get('feedback_text', ''))
                    section_ref = html_module.escape(item.get('section_reference', 'General'))
                    severity = item.get('severity', 'suggestion')

                    css_class = f'feedback feedback-{severity}'

                    html_content += f"""
                    <div class="{css_class}">
                        <div style="margin-bottom: 8px;">
                            <span class="tag">{feedback_type.upper()}</span>
                            <span class="tag">{section_ref}</span>
                        </div>
                        <p style="margin: 0;">{feedback_text}</p>
                    </div>
                    """

    # Add footer
    html_content += f"""
        <div class="footer">
            Generated by Noesis Draft-Aware Research Intelligence Platform<br>
            <strong>Note:</strong> This is AI-generated analysis. Review all suggestions critically.
        </div>
    </body>
    </html>
    """

    # Convert HTML to PDF using WeasyPrint
    pdf_bytes = HTML(string=html_content).write_pdf()

    return pdf_bytes
