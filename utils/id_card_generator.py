"""
ID Card Generator — Student Login ID generation + PDF card/slip generators.
Consolidated: student-ID logic lives in student_id_generator.py.
PDF generators use reportlab for ID cards and salary slips.
"""
from utils.student_id_generator import (
    generate_student_registration_id,
    _to_base36,
    _random_alphanum,
    _class_code,
)

# QR code secret for tamper-proof verification
QR_SECRET = "vedaflow_id_card_secret_2025"

# Re-export for backward compatibility
__all__ = [
    "generate_student_registration_id",
    "generate_student_id_card_pdf",
    "generate_employee_id_card_pdf",
    "generate_teacher_id_card_pdf",
    "generate_visitor_card_pdf",
    "generate_salary_slip_pdf",
    "QR_SECRET",
]


# ═══════════════════════════════════════════════════════════
# STUDENT ID CARD PDF
# ═══════════════════════════════════════════════════════════

def generate_student_id_card_pdf(school_data: dict, student_data: dict) -> bytes:
    """
    Generate a student ID card as PDF bytes.
    school_data: name, logo_url, motto, address, phone, landline, website
    student_data: name, student_id, roll_number, admission_number, dob,
                  blood_group, photo_url, father_name, mother_name,
                  emergency_contact, address, class_name, valid_from, valid_to
    """
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    card_w = 86 * mm   # standard ID card width
    card_h = 54 * mm   # standard ID card height
    page_w, page_h = A4

    c = canvas.Canvas(buf, pagesize=A4)

    # Center card on page
    x0 = (page_w - card_w) / 2
    y0 = (page_h - card_h) / 2

    # ── Card border ──
    c.setStrokeColor(HexColor("#1a73e8"))
    c.setLineWidth(2)
    c.roundRect(x0, y0, card_w, card_h, 3 * mm)

    # ── Header bar ──
    header_h = 14 * mm
    c.setFillColor(HexColor("#1a73e8"))
    c.rect(x0 + 1, y0 + card_h - header_h - 1, card_w - 2, header_h, fill=True, stroke=False)

    # School name
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    school_name = school_data.get("name", "School Name")
    c.drawCentredString(x0 + card_w / 2, y0 + card_h - 8 * mm, school_name[:40])

    # Motto (if fits)
    motto = school_data.get("motto", "")
    if motto:
        c.setFont("Helvetica-Oblique", 6)
        c.drawCentredString(x0 + card_w / 2, y0 + card_h - 12 * mm, motto[:50])

    # ── Photo placeholder ──
    photo_size = 20 * mm
    photo_x = x0 + 4 * mm
    photo_y = y0 + card_h - header_h - photo_size - 3 * mm
    c.setStrokeColor(HexColor("#cccccc"))
    c.setLineWidth(0.5)
    c.rect(photo_x, photo_y, photo_size, photo_size)
    c.setFillColor(HexColor("#f0f0f0"))
    c.rect(photo_x, photo_y, photo_size, photo_size, fill=True, stroke=True)
    c.setFillColor(HexColor("#999999"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(photo_x + photo_size / 2, photo_y + photo_size / 2, "PHOTO")

    # ── Student details ──
    details_x = photo_x + photo_size + 4 * mm
    details_y = y0 + card_h - header_h - 5 * mm
    line_h = 3.5 * mm

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(details_x, details_y, student_data.get("name", "")[:25])
    details_y -= line_h + 1 * mm

    fields = [
        ("Class", student_data.get("class_name", "")),
        ("Roll No", student_data.get("roll_number", "")),
        ("DOB", student_data.get("dob", "")),
        ("Blood Grp", student_data.get("blood_group", "")),
    ]
    c.setFont("Helvetica", 6)
    for label, val in fields:
        if val:
            c.setFont("Helvetica-Bold", 6)
            c.drawString(details_x, details_y, f"{label}: ")
            c.setFont("Helvetica", 6)
            c.drawString(details_x + 18 * mm, details_y, str(val)[:20])
            details_y -= line_h

    # ── Footer bar ──
    footer_h = 8 * mm
    c.setFillColor(HexColor("#e8f0fe"))
    c.rect(x0 + 1, y0 + 1, card_w - 2, footer_h, fill=True, stroke=False)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 5)
    contact = student_data.get("emergency_contact", "")
    father = student_data.get("father_name", "")
    if father:
        c.drawString(x0 + 4 * mm, y0 + 4.5 * mm, f"Father: {father[:25]}")
    if contact:
        c.drawString(x0 + 4 * mm, y0 + 1.5 * mm, f"Emergency: {contact}")

    # Validity
    valid_from = student_data.get("valid_from", "")
    valid_to = student_data.get("valid_to", "")
    if valid_from and valid_to:
        c.setFont("Helvetica", 5)
        c.drawRightString(x0 + card_w - 4 * mm, y0 + 1.5 * mm, f"Valid: {valid_from} - {valid_to}")

    c.showPage()
    c.save()
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# SALARY SLIP PDF
# ═══════════════════════════════════════════════════════════

def generate_salary_slip_pdf(school_data: dict, salary_data: dict) -> bytes:
    """
    Generate a salary slip as PDF bytes.
    school_data: name, address, logo_url
    salary_data: employee_name, employee_code, designation, department,
                 month, year, basic, hra, da, conveyance, medical, special,
                 pf, esi, tds, other_ded, gross, deductions, net,
                 days_present, days_absent, working_days
    """
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm, cm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=15 * mm, bottomMargin=15 * mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("SlipTitle", parent=styles["Heading1"],
                                  fontSize=14, alignment=TA_CENTER,
                                  spaceAfter=2 * mm, textColor=HexColor("#1a73e8"))
    subtitle_style = ParagraphStyle("SlipSubtitle", parent=styles["Normal"],
                                     fontSize=8, alignment=TA_CENTER,
                                     spaceAfter=4 * mm, textColor=HexColor("#666666"))
    label_style = ParagraphStyle("Label", parent=styles["Normal"],
                                  fontSize=9, textColor=HexColor("#333333"))
    value_style = ParagraphStyle("Value", parent=styles["Normal"],
                                  fontSize=9, fontName="Helvetica-Bold")
    month_names = {1: "January", 2: "February", 3: "March", 4: "April",
                   5: "May", 6: "June", 7: "July", 8: "August",
                   9: "September", 10: "October", 11: "November", 12: "December"}

    elements = []

    # Header
    school_name = school_data.get("name", "School")
    school_addr = school_data.get("address", "")
    month = salary_data.get("month", 1)
    year = salary_data.get("year", 2025)
    month_name = month_names.get(month, str(month))

    elements.append(Paragraph(school_name, title_style))
    if school_addr:
        elements.append(Paragraph(school_addr, subtitle_style))
    elements.append(Paragraph(f"Salary Slip for {month_name} {year}", ParagraphStyle(
        "MonthTitle", parent=styles["Heading2"], fontSize=11, alignment=TA_CENTER,
        spaceAfter=6 * mm, textColor=HexColor("#333333"))))
    elements.append(Spacer(1, 3 * mm))

    # Employee info table
    emp_data = [
        [Paragraph("<b>Employee Name</b>", label_style),
         Paragraph(salary_data.get("employee_name", ""), value_style),
         Paragraph("<b>Employee Code</b>", label_style),
         Paragraph(salary_data.get("employee_code", ""), value_style)],
        [Paragraph("<b>Designation</b>", label_style),
         Paragraph(salary_data.get("designation", ""), value_style),
         Paragraph("<b>Department</b>", label_style),
         Paragraph(salary_data.get("department", ""), value_style)],
        [Paragraph("<b>Working Days</b>", label_style),
         Paragraph(str(salary_data.get("working_days", "")), value_style),
         Paragraph("<b>Days Present</b>", label_style),
         Paragraph(str(salary_data.get("days_present", "")), value_style)],
    ]
    emp_table = Table(emp_data, colWidths=[35 * mm, 45 * mm, 35 * mm, 45 * mm])
    emp_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#f5f7fa")),
        ("BACKGROUND", (2, 0), (2, -1), HexColor("#f5f7fa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(emp_table)
    elements.append(Spacer(1, 5 * mm))

    # Earnings & Deductions side by side
    fmt = lambda v: f"{float(v):,.2f}" if v else "0.00"

    earnings = [
        ["Earnings", "Amount"],
        ["Basic Salary", fmt(salary_data.get("basic", 0))],
        ["HRA", fmt(salary_data.get("hra", 0))],
        ["DA", fmt(salary_data.get("da", 0))],
        ["Conveyance", fmt(salary_data.get("conveyance", 0))],
        ["Medical", fmt(salary_data.get("medical", 0))],
        ["Special Allowance", fmt(salary_data.get("special", 0))],
        ["", ""],
        ["Gross Salary", fmt(salary_data.get("gross", 0))],
    ]

    deductions = [
        ["Deductions", "Amount"],
        ["PF", fmt(salary_data.get("pf", 0))],
        ["ESI", fmt(salary_data.get("esi", 0))],
        ["TDS", fmt(salary_data.get("tds", 0))],
        ["Other Deductions", fmt(salary_data.get("other_ded", 0))],
        ["", ""],
        ["", ""],
        ["", ""],
        ["Total Deductions", fmt(salary_data.get("deductions", 0))],
    ]

    earn_table = Table(earnings, colWidths=[50 * mm, 28 * mm])
    earn_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1a73e8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#e8f0fe")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))

    ded_table = Table(deductions, colWidths=[50 * mm, 28 * mm])
    ded_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#dddddd")),
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#e53935")),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#fce4ec")),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))

    combined = Table([[earn_table, ded_table]], colWidths=[80 * mm, 80 * mm])
    combined.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elements.append(combined)
    elements.append(Spacer(1, 6 * mm))

    # Net Salary
    net_data = [["Net Salary Payable", fmt(salary_data.get("net", 0))]]
    net_table = Table(net_data, colWidths=[120 * mm, 40 * mm])
    net_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HexColor("#1a73e8")),
        ("TEXTCOLOR", (0, 0), (-1, -1), white),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 10 * mm))

    # Footer
    elements.append(Paragraph(
        "This is a computer-generated document and does not require a signature.",
        ParagraphStyle("Footer", parent=styles["Normal"], fontSize=7,
                       alignment=TA_CENTER, textColor=HexColor("#999999"))))

    doc.build(elements)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# EMPLOYEE ID CARD PDF
# ═══════════════════════════════════════════════════════════

def generate_employee_id_card_pdf(school_data: dict, employee_data: dict) -> bytes:
    """Generate an employee/non-teaching staff ID card as PDF bytes."""
    return _generate_staff_card_pdf(school_data, employee_data, card_color="#7C3AED", role_label="STAFF")


# ═══════════════════════════════════════════════════════════
# TEACHER ID CARD PDF
# ═══════════════════════════════════════════════════════════

def generate_teacher_id_card_pdf(school_data: dict, teacher_data: dict) -> bytes:
    """Generate a teacher ID card as PDF bytes."""
    return _generate_staff_card_pdf(school_data, teacher_data, card_color="#059669", role_label="TEACHER")


# ═══════════════════════════════════════════════════════════
# VISITOR / GUEST CARD PDF
# ═══════════════════════════════════════════════════════════

def generate_visitor_card_pdf(school_data: dict, visitor_data: dict) -> bytes:
    """
    Generate a visitor/guest pass as PDF bytes.
    visitor_data: name, purpose, visiting_whom, phone, date, valid_until
    """
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    card_w = 86 * mm
    card_h = 54 * mm
    page_w, page_h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    x0 = (page_w - card_w) / 2
    y0 = (page_h - card_h) / 2

    # Card border — orange for visitor
    c.setStrokeColor(HexColor("#EA580C"))
    c.setLineWidth(2)
    c.roundRect(x0, y0, card_w, card_h, 3 * mm)

    # Header bar
    header_h = 16 * mm
    c.setFillColor(HexColor("#EA580C"))
    c.rect(x0 + 1, y0 + card_h - header_h - 1, card_w - 2, header_h, fill=True, stroke=False)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(x0 + card_w / 2, y0 + card_h - 8 * mm, school_data.get("name", "School")[:35])
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(x0 + card_w / 2, y0 + card_h - 13 * mm, "VISITOR PASS")

    # Visitor details
    details_x = x0 + 6 * mm
    details_y = y0 + card_h - header_h - 5 * mm
    line_h = 4 * mm

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(details_x, details_y, visitor_data.get("name", "Guest")[:30])
    details_y -= line_h + 1 * mm

    fields = [
        ("Purpose", visitor_data.get("purpose", "")),
        ("Visiting", visitor_data.get("visiting_whom", "")),
        ("Phone", visitor_data.get("phone", "")),
        ("Date", visitor_data.get("date", "")),
    ]
    c.setFont("Helvetica", 6.5)
    for label, val in fields:
        if val:
            c.setFont("Helvetica-Bold", 6.5)
            c.drawString(details_x, details_y, f"{label}: ")
            c.setFont("Helvetica", 6.5)
            c.drawString(details_x + 16 * mm, details_y, str(val)[:30])
            details_y -= line_h

    # Footer
    footer_h = 6 * mm
    c.setFillColor(HexColor("#FFF7ED"))
    c.rect(x0 + 1, y0 + 1, card_w - 2, footer_h, fill=True, stroke=False)
    c.setFillColor(HexColor("#9A3412"))
    c.setFont("Helvetica-Bold", 5)
    valid = visitor_data.get("valid_until", "Today Only")
    c.drawCentredString(x0 + card_w / 2, y0 + 2 * mm, f"Valid: {valid} | Must be returned at exit")

    c.showPage()
    c.save()
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# SHARED STAFF CARD GENERATOR (Teacher / Employee)
# ═══════════════════════════════════════════════════════════

def _generate_staff_card_pdf(school_data: dict, person_data: dict,
                              card_color: str = "#1a73e8", role_label: str = "STAFF") -> bytes:
    """Internal: generates teacher or employee ID card PDF."""
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    card_w = 86 * mm
    card_h = 54 * mm
    page_w, page_h = A4
    c = canvas.Canvas(buf, pagesize=A4)
    x0 = (page_w - card_w) / 2
    y0 = (page_h - card_h) / 2

    # Card border
    c.setStrokeColor(HexColor(card_color))
    c.setLineWidth(2)
    c.roundRect(x0, y0, card_w, card_h, 3 * mm)

    # Header bar
    header_h = 14 * mm
    c.setFillColor(HexColor(card_color))
    c.rect(x0 + 1, y0 + card_h - header_h - 1, card_w - 2, header_h, fill=True, stroke=False)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x0 + card_w / 2, y0 + card_h - 8 * mm, school_data.get("name", "School")[:40])
    motto = school_data.get("motto", "")
    if motto:
        c.setFont("Helvetica-Oblique", 6)
        c.drawCentredString(x0 + card_w / 2, y0 + card_h - 12 * mm, motto[:50])

    # Photo placeholder
    photo_size = 20 * mm
    photo_x = x0 + 4 * mm
    photo_y = y0 + card_h - header_h - photo_size - 3 * mm
    c.setFillColor(HexColor("#f0f0f0"))
    c.setStrokeColor(HexColor("#cccccc"))
    c.setLineWidth(0.5)
    c.rect(photo_x, photo_y, photo_size, photo_size, fill=True, stroke=True)
    c.setFillColor(HexColor("#999999"))
    c.setFont("Helvetica", 6)
    c.drawCentredString(photo_x + photo_size / 2, photo_y + photo_size / 2, "PHOTO")

    # Role badge
    badge_w = 18 * mm
    badge_h = 4.5 * mm
    c.setFillColor(HexColor(card_color))
    c.roundRect(photo_x, photo_y - badge_h - 1 * mm, badge_w, badge_h, 2 * mm, fill=True, stroke=False)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 5.5)
    c.drawCentredString(photo_x + badge_w / 2, photo_y - badge_h + 0.5 * mm, role_label)

    # Details
    details_x = photo_x + photo_size + 4 * mm
    details_y = y0 + card_h - header_h - 5 * mm
    line_h = 3.5 * mm

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(details_x, details_y, person_data.get("name", "")[:25])
    details_y -= line_h + 1 * mm

    fields = [
        ("Designation", person_data.get("designation", "")),
        ("Department", person_data.get("department", "")),
        ("Code", person_data.get("employee_code", "")),
        ("DOB", person_data.get("dob", "")),
        ("Blood Grp", person_data.get("blood_group", "")),
    ]
    c.setFont("Helvetica", 6)
    for label, val in fields:
        if val:
            c.setFont("Helvetica-Bold", 6)
            c.drawString(details_x, details_y, f"{label}: ")
            c.setFont("Helvetica", 6)
            c.drawString(details_x + 20 * mm, details_y, str(val)[:20])
            details_y -= line_h

    # Footer
    footer_h = 8 * mm
    c.setFillColor(HexColor("#f0f4ff"))
    c.rect(x0 + 1, y0 + 1, card_w - 2, footer_h, fill=True, stroke=False)
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 5)
    contact_name = person_data.get("emergency_contact_name", "")
    contact_phone = person_data.get("emergency_contact_phone", person_data.get("emergency_contact", ""))
    if contact_name:
        c.drawString(x0 + 4 * mm, y0 + 4.5 * mm, f"Emergency: {contact_name[:20]}")
    if contact_phone:
        c.drawString(x0 + 4 * mm, y0 + 1.5 * mm, f"Phone: {contact_phone}")
    valid_from = person_data.get("valid_from", "")
    valid_to = person_data.get("valid_to", "")
    if valid_from and valid_to:
        c.drawRightString(x0 + card_w - 4 * mm, y0 + 1.5 * mm, f"Valid: {valid_from} - {valid_to}")

    c.showPage()
    c.save()
    return buf.getvalue()
