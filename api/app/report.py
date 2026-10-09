"""Student result PDF, built with ReportLab.

Deliberately plain: a result sheet gets printed, filed and occasionally
photocopied, so it needs legible structure far more than it needs styling.
"""
from __future__ import annotations

import io
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
    TableStyle,
)

from . import blobs

logger = logging.getLogger(__name__)

# Matches the app's primary (oklch(0.5106 0.2301 276.9656)) closely enough
# that a printed report and the screen read as one product.
BRAND = colors.HexColor("#4B36C9")
MUTED = colors.HexColor("#5A5A5A")
LINE = colors.HexColor("#CFCFCF")


def _kv_table(rows: list[tuple[str, str]], width: float) -> Table:
    t = Table([[k, v] for k, v in rows], colWidths=[width * 0.32, width * 0.68])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), MUTED),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, -2), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return t


def _fit_image(img_bytes: bytes, max_width: float, max_height: float):
    """Scale a sheet image to fit the page, preserving its aspect ratio.

    An OMR sheet is tall and narrow, so height is usually the binding
    constraint rather than width -- scaling on width alone would push the
    bottom of the grid onto a second page and split it across the fold.

    Takes raw bytes rather than a path, so it works the same whether a sheet
    lives on disk or in Postgres (see app/blobs.py) -- ReportLab accepts a
    file-like object anywhere it takes a path, so a fresh BytesIO per call
    stands in for one.

    Returns None rather than raising: an unreadable image must not cost the
    student their result sheet.
    """
    try:
        from reportlab.lib.utils import ImageReader

        width, height = ImageReader(io.BytesIO(img_bytes)).getSize()
        if not width or not height:
            return None
        scale = min(max_width / width, max_height / height)
        return RLImage(io.BytesIO(img_bytes), width=width * scale, height=height * scale)
    except Exception:                                 # noqa: BLE001
        logger.exception("could not place a sheet image in the report")
        return None


def build_student_report(test: dict, submission: dict, candidate: dict,
                         evaluation: dict, items: list[dict]) -> bytes:
    """Build the PDF in memory and return its bytes.

    Returning bytes, not writing to a path, is what lets the caller store the
    result through app/blobs.py without this module knowing whether that
    means a file on disk or a row in Postgres.
    """
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Result - {test.get('name', '')}",
        author="Smart OMR Evaluator")
    avail = doc.width

    h1 = ParagraphStyle("h1", parent=styles["Title"], fontSize=17,
                        textColor=BRAND, spaceAfter=2, alignment=0)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9.5,
                         textColor=MUTED, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11.5,
                        textColor=BRAND, spaceBefore=12, spaceAfter=5)

    story = [Paragraph("Examination Result", h1)]
    inst = test.get("institution_name") or "Smart OMR Evaluator"
    story.append(Paragraph(f"{inst} &nbsp;&bull;&nbsp; Result sheet", sub))

    story.append(Paragraph("Candidate", h2))
    story.append(_kv_table([
        ("Name", candidate.get("student_name") or "-"),
        ("Roll Number", candidate.get("roll_no") or "-"),
        ("Registration No.", candidate.get("registration_no") or "-"),
        ("Class / Standard", candidate.get("class_std") or "-"),
        ("Section", candidate.get("section") or "-"),
    ], avail))

    story.append(Paragraph("Examination", h2))
    story.append(_kv_table([
        ("Test", test.get("name") or "-"),
        ("Subject", test.get("subject") or "-"),
        ("Date", str(test.get("exam_date") or "-")),
        ("Sheet Layout", submission.get("layout_used") or test.get("layout") or "-"),
        ("Evaluated On", str(evaluation.get("evaluated_at") or "-")[:19]),
    ], avail))

    # Headline numbers.
    story.append(Paragraph("Result", h2))
    pct = float(evaluation.get("percentage") or 0)
    summary = Table([
        ["Marks Obtained", "Maximum", "Percentage", "Grade"],
        [f"{float(evaluation.get('total_marks') or 0):g}",
         f"{float(evaluation.get('max_marks') or 0):g}",
         f"{pct:.2f}%",
         evaluation.get("grade") or "-"],
    ], colWidths=[avail / 4.0] * 4)
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("FONTSIZE", (0, 1), (-1, 1), 15),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 1), (-1, 1), 8),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
    ]))
    story.append(summary)
    story.append(Spacer(1, 8))

    story.append(_kv_table([
        ("Correct", str(evaluation.get("correct_count", 0))),
        ("Incorrect", str(evaluation.get("wrong_count", 0))),
        ("Unanswered", str(evaluation.get("unattempted_count", 0))),
        ("Invalid / Multiple", str(evaluation.get("invalid_count", 0))),
        ("Not in answer key", str(evaluation.get("unscored_count", 0))),
    ], avail))

    subject_scores = evaluation.get("subject_scores") or {}
    if len(subject_scores) > 1:
        story.append(Paragraph("Subject-wise Marks", h2))
        rows = [["Subject", "Marks"]] + [[k, f"{float(v):g}"]
                                         for k, v in subject_scores.items()]
        t = Table(rows, colWidths=[avail * 0.7, avail * 0.3])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F0F6")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.25, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(t)

    # The sheet itself, as read and as photographed.  A printed result that a
    # student can dispute needs the evidence attached: the overlay shows which
    # bubble the machine credited for every question, so a disagreement can be
    # settled against the paper rather than argued about.
    sheets = [
        (submission.get("annotated_path"), "As read by the scanner",
         "Each ring marks the bubble detected for that question."),
        (submission.get("image_path"), "Original scan",
         "The sheet exactly as it was photographed."),
    ]
    # Loaded through blobs.load(), not read as a path: the token in each
    # *_path column may point at local disk or at a Postgres row depending on
    # STORAGE_BACKEND, and only blobs.py knows which.
    sheets = [(blobs.load(p), t, c) for p, t, c in sheets if p]
    sheets = [(data, t, c) for data, t, c in sheets if data is not None]
    if sheets:
        story.append(PageBreak())
        story.append(Paragraph("Answer Sheet", h2))
        for i, (img_bytes, title, caption) in enumerate(sheets):
            if i:
                story.append(PageBreak())
            story.append(Paragraph(title, ParagraphStyle(
                "imgTitle", parent=styles["Normal"], fontSize=10,
                fontName="Helvetica-Bold", spaceAfter=2)))
            story.append(Paragraph(caption, ParagraphStyle(
                "imgCap", parent=styles["Normal"], fontSize=8,
                textColor=MUTED, spaceAfter=6)))
            flowable = _fit_image(img_bytes, avail, doc.height - 40 * mm)
            if flowable is not None:
                story.append(flowable)

    # Question-wise detail.  Attempted questions first matters less than
    # keeping question order, which is how a student checks their own paper.
    story.append(PageBreak() if sheets else Spacer(1, 1))
    story.append(Paragraph("Question-wise Detail", h2))
    header = ["Q", "Marked", "Correct", "Result", "Marks"]
    data = [header]
    label = {"correct": "Correct", "wrong": "Incorrect",
             "unattempted": "Not answered", "invalid": "Invalid",
             "unscored": "Not in key"}
    for it in items:
        data.append([
            str(it["question_no"]),
            it.get("marked_option") or "-",
            it.get("expected_option") or "-",
            label.get(it.get("status"), it.get("status") or "-"),
            f"{float(it.get('marks') or 0):g}",
        ])

    col = [avail * 0.10, avail * 0.18, avail * 0.18, avail * 0.36, avail * 0.18]
    table = Table(data, colWidths=col, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F0F6")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (2, -1), "CENTER"),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    # Colour the verdict cell so a parent can scan the sheet without reading it.
    for i, it in enumerate(items, start=1):
        status = it.get("status")
        if status == "correct":
            style.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#14863C")))
        elif status == "wrong":
            style.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#C0392B")))
        elif status in ("invalid", "unscored"):
            style.append(("TEXTCOLOR", (3, i), (3, i), colors.HexColor("#B8860B")))
        else:
            style.append(("TEXTCOLOR", (3, i), (3, i), MUTED))
    table.setStyle(TableStyle(style))
    story.append(table)

    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Generated by Smart OMR Evaluator. Answers were read automatically and "
        "scored against the answer key stored for this test. "
        f"Submission #{submission.get('id')}.",
        ParagraphStyle("foot", parent=styles["Normal"], fontSize=7.5,
                       textColor=MUTED)))

    doc.build(story)
    return buffer.getvalue()
