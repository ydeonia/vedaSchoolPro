"""
Report Card PDF Generator — On-demand PDF generation using ReportLab.
Reads template config + student marks → renders professional PDF.
"""
import io
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter, landscape
from reportlab.lib.units import mm, inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, HRFlowable
from reportlab.graphics.shapes import Drawing, Line


def calculate_grade(percentage):
    if percentage >= 91: return "A1"
    elif percentage >= 81: return "A2"
    elif percentage >= 71: return "B1"
    elif percentage >= 61: return "B2"
    elif percentage >= 51: return "C1"
    elif percentage >= 41: return "C2"
    elif percentage >= 33: return "D"
    else: return "E"


def generate_report_card_pdf(
    school_info,
    student_info,
    subjects_marks,
    result_info,
    template_config=None,
    attendance_info=None,
):
    """
    Generate a professional report card PDF.

    Args:
        school_info: dict with name, address, phone, logo_url, affiliation, motto
        student_info: dict with name, class_name, section, roll, admission, father_name, mother_name, dob, photo_url
        subjects_marks: list of dicts with subject, max_marks, marks_obtained, special_code, grace_marks, final_marks, grade
        result_info: dict with total, max_total, percentage, grade, rank, result_status, remarks
        template_config: optional dict from ReportCardTemplate.layout_json
        attendance_info: optional dict with total_days, present_days, percentage
    """
    buffer = io.BytesIO()

    page_size = A4
    if template_config:
        if template_config.get("page_size") == "letter":
            page_size = letter
        if template_config.get("orientation") == "landscape":
            page_size = landscape(page_size)

    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        topMargin=15*mm, bottomMargin=15*mm,
        leftMargin=15*mm, rightMargin=15*mm
    )

    styles = getSampleStyleSheet()
    elements = []

    # Custom styles
    title_style = ParagraphStyle(
        "RCTitle", parent=styles["Heading1"],
        fontSize=16, alignment=TA_CENTER, spaceAfter=2*mm,
        textColor=colors.HexColor("#1E293B"),
        fontName="Helvetica-Bold"
    )
    subtitle_style = ParagraphStyle(
        "RCSubtitle", parent=styles["Normal"],
        fontSize=9, alignment=TA_CENTER, spaceAfter=1*mm,
        textColor=colors.HexColor("#64748B")
    )
    label_style = ParagraphStyle(
        "RCLabel", parent=styles["Normal"],
        fontSize=9, textColor=colors.HexColor("#64748B"),
        fontName="Helvetica"
    )
    value_style = ParagraphStyle(
        "RCValue", parent=styles["Normal"],
        fontSize=10, textColor=colors.HexColor("#1E293B"),
        fontName="Helvetica-Bold"
    )

    # ─── HEADER ───────────────────────────
    elements.append(Paragraph(school_info.get("name", "School"), title_style))
    if school_info.get("address"):
        elements.append(Paragraph(school_info["address"], subtitle_style))
    if school_info.get("affiliation"):
        elements.append(Paragraph(f"Affiliation No: {school_info['affiliation']}", subtitle_style))
    elements.append(Spacer(1, 2*mm))

    # Exam title
    exam_name = result_info.get("exam_name", "Examination")
    academic_year = result_info.get("academic_year", "")
    elements.append(Paragraph(
        f"<b>{exam_name}</b> — Academic Year {academic_year}",
        ParagraphStyle("ExamTitle", parent=styles["Normal"], fontSize=11,
                       alignment=TA_CENTER, textColor=colors.HexColor("#4F46E5"),
                       fontName="Helvetica-Bold", spaceAfter=4*mm)
    ))

    elements.append(HRFlowable(width="100%", thickness=1.5,
                                color=colors.HexColor("#E2E8F0"), spaceAfter=4*mm))

    # ─── STUDENT INFO TABLE ───────────────
    info_data = [
        [Paragraph("<b>Student Name</b>", label_style),
         Paragraph(student_info.get("name", ""), value_style),
         Paragraph("<b>Class / Section</b>", label_style),
         Paragraph(f"{student_info.get('class_name', '')} - {student_info.get('section', '')}", value_style)],
        [Paragraph("<b>Roll Number</b>", label_style),
         Paragraph(str(student_info.get("roll", "")), value_style),
         Paragraph("<b>Admission No</b>", label_style),
         Paragraph(str(student_info.get("admission", "")), value_style)],
        [Paragraph("<b>Father's Name</b>", label_style),
         Paragraph(student_info.get("father_name", ""), value_style),
         Paragraph("<b>Mother's Name</b>", label_style),
         Paragraph(student_info.get("mother_name", ""), value_style)],
    ]
    if student_info.get("dob"):
        info_data.append([
            Paragraph("<b>Date of Birth</b>", label_style),
            Paragraph(str(student_info["dob"]), value_style),
            Paragraph("", label_style), Paragraph("", value_style),
        ])

    info_table = Table(info_data, colWidths=[80, 140, 80, 140])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 5*mm))

    # ─── MARKS TABLE ──────────────────────
    header_style = ParagraphStyle("TH", parent=styles["Normal"], fontSize=9,
                                   fontName="Helvetica-Bold", textColor=colors.white,
                                   alignment=TA_CENTER)
    cell_style = ParagraphStyle("TD", parent=styles["Normal"], fontSize=9,
                                 alignment=TA_CENTER)
    cell_left = ParagraphStyle("TDL", parent=styles["Normal"], fontSize=9)

    table_data = [[
        Paragraph("S.No.", header_style),
        Paragraph("Subject", header_style),
        Paragraph("Max Marks", header_style),
        Paragraph("Marks Obtained", header_style),
        Paragraph("Grace", header_style),
        Paragraph("Final Marks", header_style),
        Paragraph("Grade", header_style),
    ]]

    for idx, subj in enumerate(subjects_marks, 1):
        special = subj.get("special_code")
        if special:
            marks_display = special
            final_display = special
            grace_display = "-"
            grade_display = "-"
        else:
            marks_display = str(subj.get("marks_obtained", 0))
            grace = subj.get("grace_marks", 0)
            grace_display = str(grace) if grace > 0 else "-"
            final_display = str(subj.get("final_marks", subj.get("marks_obtained", 0)))
            grade_display = subj.get("grade", "")

        table_data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(subj.get("subject", ""), cell_left),
            Paragraph(str(subj.get("max_marks", 100)), cell_style),
            Paragraph(marks_display, cell_style),
            Paragraph(grace_display, cell_style),
            Paragraph(final_display, cell_style),
            Paragraph(grade_display, cell_style),
        ])

    # Total row
    table_data.append([
        Paragraph("", cell_style),
        Paragraph("<b>TOTAL</b>", cell_left),
        Paragraph(f"<b>{result_info.get('max_total', 0)}</b>", cell_style),
        Paragraph("", cell_style),
        Paragraph("", cell_style),
        Paragraph(f"<b>{result_info.get('total', 0)}</b>", cell_style),
        Paragraph("", cell_style),
    ])

    col_widths = [30, 130, 55, 65, 40, 55, 45]
    marks_table = Table(table_data, colWidths=col_widths, repeatRows=1)

    primary_color = colors.HexColor("#4F46E5")
    marks_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), primary_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F8FAFC")]),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF2FF")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    elements.append(marks_table)
    elements.append(Spacer(1, 5*mm))

    # ─── RESULT SUMMARY ──────────────────
    pct = result_info.get("percentage", 0)
    grade = result_info.get("grade", calculate_grade(pct))
    rank = result_info.get("rank")
    status = result_info.get("result_status", "promoted")
    status_display = status.replace("_", " ").title()

    summary_data = [
        [Paragraph("<b>Percentage</b>", label_style),
         Paragraph(f"<b>{pct:.1f}%</b>", value_style),
         Paragraph("<b>Overall Grade</b>", label_style),
         Paragraph(f"<b>{grade}</b>", value_style)],
        [Paragraph("<b>Class Rank</b>", label_style),
         Paragraph(f"<b>{rank or '-'}</b>", value_style),
         Paragraph("<b>Result</b>", label_style),
         Paragraph(f"<b>{status_display}</b>", value_style)],
    ]
    summary_table = Table(summary_data, colWidths=[80, 100, 80, 100])
    summary_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 5*mm))

    # ─── ATTENDANCE (if available) ────────
    if attendance_info and attendance_info.get("total_days"):
        att_data = [[
            Paragraph("<b>Total Working Days</b>", label_style),
            Paragraph(str(attendance_info["total_days"]), value_style),
            Paragraph("<b>Days Present</b>", label_style),
            Paragraph(str(attendance_info.get("present_days", 0)), value_style),
            Paragraph("<b>Attendance %</b>", label_style),
            Paragraph(f"{attendance_info.get('percentage', 0):.1f}%", value_style),
        ]]
        att_table = Table(att_data, colWidths=[80, 50, 65, 50, 60, 50])
        att_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        elements.append(att_table)
        elements.append(Spacer(1, 3*mm))

    # ─── REMARKS ──────────────────────────
    if result_info.get("remarks"):
        elements.append(Paragraph(
            f"<b>Class Teacher's Remarks:</b> {result_info['remarks']}",
            ParagraphStyle("Remarks", parent=styles["Normal"], fontSize=9, spaceAfter=3*mm)
        ))

    # ─── GRADING SCALE ────────────────────
    elements.append(Spacer(1, 5*mm))
    scale_data = [[
        Paragraph("<b>Grading Scale</b>", ParagraphStyle("GS", parent=styles["Normal"],
                   fontSize=8, fontName="Helvetica-Bold")),
    ]]
    scale_items = "A1 (≥91%) | A2 (≥81%) | B1 (≥71%) | B2 (≥61%) | C1 (≥51%) | C2 (≥41%) | D (≥33%) | E (<33%)"
    elements.append(Paragraph(
        f"<i>{scale_items}</i>",
        ParagraphStyle("Scale", parent=styles["Normal"], fontSize=7,
                       textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)
    ))

    elements.append(Spacer(1, 10*mm))

    # ─── SIGNATURES ───────────────────────
    sig_data = [[
        Paragraph("Class Teacher", ParagraphStyle("Sig", parent=styles["Normal"],
                   fontSize=9, alignment=TA_CENTER)),
        Paragraph("", label_style),
        Paragraph("Principal", ParagraphStyle("Sig2", parent=styles["Normal"],
                   fontSize=9, alignment=TA_CENTER)),
    ]]
    sig_line = [[
        Paragraph("_________________", ParagraphStyle("SL", parent=styles["Normal"],
                   fontSize=9, alignment=TA_CENTER)),
        Paragraph("", label_style),
        Paragraph("_________________", ParagraphStyle("SL2", parent=styles["Normal"],
                   fontSize=9, alignment=TA_CENTER)),
    ]]
    sig_table = Table(sig_line + sig_data, colWidths=[150, 120, 150])
    sig_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(sig_table)

    # ─── FOOTER ───────────────────────────
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(
        f"Generated on {datetime.now().strftime('%d %b %Y at %H:%M')} — This is a computer-generated document.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                       textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER)
    ))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
