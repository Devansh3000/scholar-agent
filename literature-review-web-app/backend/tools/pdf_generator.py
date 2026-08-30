"""
PDF generator tool for the Literature Review Web Application.

Converts a :class:`~models.paper.LiteratureReview` object into a formatted
A4 PDF document using ReportLab.  The output includes a title page, table of
contents, all review sections, and a bibliography.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from models.paper import LiteratureReview

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# 2 cm margins expressed in points  (1 inch = 72 pt; 1 inch = 2.54 cm)
_MARGIN: float = 72 / 2.54 * 2  # ≈ 56.69 points


# ---------------------------------------------------------------------------
# Page-numbering callback
# ---------------------------------------------------------------------------


def _on_later_pages(canvas, doc) -> None:  # type: ignore[type-arg]
    """Draw a right-aligned page number at the bottom of every page after the first."""
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    page_num = f"Page {doc.page}"
    canvas.drawRightString(A4[0] - _MARGIN, _MARGIN / 2, page_num)
    canvas.restoreState()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_pdf(review: LiteratureReview, output_path: str) -> str:
    """Generate a PDF literature review document and save it to *output_path*.

    Parameters
    ----------
    review:
        The completed :class:`~models.paper.LiteratureReview` to render.
    output_path:
        Absolute or relative filesystem path where the PDF will be written.
        Parent directories are created automatically if they do not exist.

    Returns
    -------
    str
        The resolved *output_path* string after the document has been saved.

    Raises
    ------
    OSError
        If the output directory cannot be created or the file cannot be
        written.
    """
    logger.info("Generating PDF for review %r → %s", review.topic, output_path)

    # Ensure parent directory exists.
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Document setup
    # ------------------------------------------------------------------
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN,
    )

    # ------------------------------------------------------------------
    # Styles
    # ------------------------------------------------------------------
    base_styles = getSampleStyleSheet()

    heading1 = ParagraphStyle(
        "ReviewHeading1",
        parent=base_styles["Heading1"],
        spaceBefore=12,
        spaceAfter=12,
    )
    normal = ParagraphStyle(
        "ReviewNormal",
        parent=base_styles["Normal"],
        spaceBefore=12,
        spaceAfter=12,
    )
    title_style = ParagraphStyle(
        "ReviewTitle",
        parent=base_styles["Title"],
        fontSize=24,
        spaceAfter=20,
        spaceBefore=40,
    )
    subtitle_style = ParagraphStyle(
        "ReviewSubtitle",
        parent=base_styles["Normal"],
        fontSize=12,
        spaceAfter=8,
        textColor=colors.grey,
    )
    toc_item_style = ParagraphStyle(
        "ReviewTOCItem",
        parent=base_styles["Normal"],
        leftIndent=20,
        spaceBefore=4,
        spaceAfter=4,
    )

    # ------------------------------------------------------------------
    # Story (list of Flowables)
    # ------------------------------------------------------------------
    story: list = []

    # ── 1. Title page ──────────────────────────────────────────────────
    story.append(Spacer(1, 60))
    story.append(Paragraph(review.topic, title_style))
    story.append(Spacer(1, 12))

    generated_str = review.generated_at.strftime("%B %d, %Y")
    story.append(Paragraph(f"Generated: {generated_str}", subtitle_style))
    story.append(Paragraph(f"Papers reviewed: {review.paper_count}", subtitle_style))

    # ── 2. Page break ──────────────────────────────────────────────────
    story.append(PageBreak())

    # ── 3. Table of Contents (manual) ─────────────────────────────────
    story.append(Paragraph("<b>Table of Contents</b>", heading1))
    story.append(Spacer(1, 6))

    _toc_sections = [
        "Executive Summary",
        "Introduction",
        "Thematic Analysis",
        "Comparative Analysis",
        "Research Gaps",
        "Conclusion",
        "Bibliography",
    ]
    for section_name in _toc_sections:
        story.append(Paragraph(f"• {section_name}", toc_item_style))

    # ── 4. Page break ──────────────────────────────────────────────────
    story.append(PageBreak())

    # ── 5. Executive Summary ───────────────────────────────────────────
    story.append(Paragraph("<b>Executive Summary</b>", heading1))
    story.append(Paragraph(review.executive_summary, normal))

    # ── 6. Introduction ────────────────────────────────────────────────
    story.append(Paragraph("<b>Introduction</b>", heading1))
    story.append(Paragraph(review.introduction, normal))

    # ── 7. Thematic Analysis ───────────────────────────────────────────
    story.append(Paragraph("<b>Thematic Analysis</b>", heading1))
    story.append(Paragraph(review.thematic_analysis, normal))

    # Theme cluster summary table
    if review.themes:
        story.append(Spacer(1, 8))
        story.append(Paragraph("<b>Theme Cluster Summary</b>", normal))

        table_data: list[list[str]] = [["Theme", "Papers"]]
        for theme in review.themes:
            table_data.append([theme.label, str(len(theme.paper_ids))])

        theme_table = Table(
            table_data,
            colWidths=[None, 60],
            hAlign="LEFT",
        )
        theme_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4A90D9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F2F2")]),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(theme_table)
        story.append(Spacer(1, 12))

    # ── 8. Comparative Analysis ────────────────────────────────────────
    story.append(Paragraph("<b>Comparative Analysis</b>", heading1))
    story.append(Paragraph(review.comparative_analysis, normal))

    # ── 9. Research Gaps (grouped by gap_type) ────────────────────────
    story.append(Paragraph("<b>Research Gaps</b>", heading1))

    if review.research_gaps:
        # Group gaps by type
        gaps_by_type: dict[str, list] = {}
        for gap in review.research_gaps:
            gaps_by_type.setdefault(gap.gap_type, []).append(gap)

        for gap_type, gaps in gaps_by_type.items():
            story.append(Paragraph(f"<b>{gap_type.capitalize()} Gaps</b>", normal))
            for gap in gaps:
                story.append(Paragraph(f"• {gap.description}", toc_item_style))
    else:
        story.append(Paragraph(review.gaps_section, normal))

    # ── 10. Conclusion ─────────────────────────────────────────────────
    story.append(Paragraph("<b>Conclusion</b>", heading1))
    story.append(Paragraph(review.conclusion, normal))

    # ── 11. Page break ─────────────────────────────────────────────────
    story.append(PageBreak())

    # ── 12. Bibliography ───────────────────────────────────────────────
    story.append(Paragraph("<b>Bibliography</b>", heading1))

    if review.bibliography:
        for citation in review.bibliography.split("\n\n"):
            stripped = citation.strip()
            if stripped:
                story.append(Paragraph(stripped, normal))
    else:
        story.append(Paragraph("No references available.", normal))

    # ------------------------------------------------------------------
    # Build the document
    # ------------------------------------------------------------------
    doc.build(
        story,
        onFirstPage=_on_later_pages,
        onLaterPages=_on_later_pages,
    )

    logger.info("PDF written to %s", output_path)
    return output_path


__all__ = ["generate_pdf"]
