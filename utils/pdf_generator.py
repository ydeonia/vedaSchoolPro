"""PDF Generation Utilities — Fee Receipts & Report Cards"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable, Image
from reportlab.pdfgen import canvas
from io import BytesIO
from datetime import datetime
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))


def _watermark_callback(canvas_obj, doc):
    """Draw diagonal watermark on every page"""
    canvas_obj.saveState()
    canvas_obj.setFont('Helvetica-Bold', 50)
    canvas_obj.setFillColor(HexColor('#E5E7EB'))
    canvas_obj.setFillAlpha(0.15)
    width, height = A4
    canvas_obj.translate(width / 2, height / 2)
    canvas_obj.rotate(45)
    canvas_obj.drawCentredString(0, 0, "EduFlow Verified")
    canvas_obj.drawCentredString(0, -80, "Original Document")
    canvas_obj.restoreState()


def _load_signature_image(url, width=50*mm, height=20*mm):
    """Load signature image from URL path, return Image flowable or empty string"""
    if not url:
        return ''
    filepath = os.path.join(BASE_DIR, url.lstrip('/'))
    if os.path.exists(filepath):
        try:
            return Image(filepath, width=width, height=height)
        except:
            return ''
    return ''


# Colors
PRIMARY = HexColor('#4F46E5')
SUCCESS = HexColor('#059669')
DANGER = HexColor('#DC2626')
GRAY = HexColor('#6B7280')
LIGHT_GRAY = HexColor('#F3F4F6')
BORDER = HexColor('#E5E7EB')


def _get_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SchoolName', fontSize=16, leading=20, alignment=TA_CENTER, fontName='Helvetica-Bold', textColor=PRIMARY))
    styles.add(ParagraphStyle(name='DocTitle', fontSize=12, leading=16, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=4))
    styles.add(ParagraphStyle(name='FieldLabel', fontSize=8, leading=10, textColor=GRAY, fontName='Helvetica'))
    styles.add(ParagraphStyle(name='FieldValue', fontSize=10, leading=13, fontName='Helvetica-Bold'))
    styles.add(ParagraphStyle(name='SmallCenter', fontSize=8, leading=10, alignment=TA_CENTER, textColor=GRAY))
    styles.add(ParagraphStyle(name='Footer', fontSize=7, leading=9, alignment=TA_CENTER, textColor=GRAY))
    return styles


def generate_fee_receipt_pdf(school_name, receipt_data):
    """
    Generate a fee receipt PDF with school logo, motto, accreditation, fee breakup.
    receipt_data: {
        receipt_number, date, student_name, class_name, roll_number, admission_number,
        father_name, fee_name, amount_due, amount_paid, discount, balance,
        payment_mode, transaction_id, upi_id, bank_details,
        # NEW: logo_url, motto, accreditation, landline, address,
        # NEW: fee_breakup: [{name, amount}] — e.g. Tuition, Bus, Lab, Library
    }
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=20*mm, rightMargin=20*mm)
    styles = _get_styles()
    story = []

    # School header with logo
    logo_url = receipt_data.get('logo_url', '')
    logo_img = _load_signature_image(logo_url, width=18*mm, height=18*mm) if logo_url else ''

    header_elements = []
    school_header_text = f"<b>{school_name}</b>"
    motto = receipt_data.get('motto', '')
    accreditation = receipt_data.get('accreditation', '')
    address = receipt_data.get('school_address', '')
    landline = receipt_data.get('landline', '')

    if motto:
        school_header_text += f"<br/><font size='8' color='#6B7280'><i>{motto}</i></font>"
    if accreditation:
        school_header_text += f"<br/><font size='7' color='#4F46E5'>Affiliation: {accreditation}</font>"
    if address:
        school_header_text += f"<br/><font size='7' color='#6B7280'>{address}</font>"
    if landline:
        school_header_text += f"<br/><font size='7' color='#6B7280'>Tel: {landline}</font>"

    if logo_img:
        header_data = [[logo_img, Paragraph(school_header_text, styles['SchoolName'])]]
        header_table = Table(header_data, colWidths=[22*mm, 140*mm])
        header_table.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('ALIGN', (1, 0), (1, 0), 'CENTER')]))
        story.append(header_table)
    else:
        story.append(Paragraph(school_header_text, styles['SchoolName']))

    story.append(Spacer(1, 2*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=3*mm))
    story.append(Paragraph("FEE RECEIPT", styles['DocTitle']))
    story.append(Spacer(1, 4*mm))

    # Receipt info row
    info_data = [
        [Paragraph("<b>Receipt No:</b>", styles['Normal']),
         Paragraph(receipt_data.get('receipt_number', ''), styles['Normal']),
         Paragraph("<b>Date:</b>", styles['Normal']),
         Paragraph(receipt_data.get('date', datetime.now().strftime('%d %b %Y')), styles['Normal'])],
    ]
    info_table = Table(info_data, colWidths=[70, 140, 50, 140])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 4*mm))

    # Student details
    student_data = [
        ['Student Name', receipt_data.get('student_name', ''), 'Class', receipt_data.get('class_name', '')],
        ['Roll No', receipt_data.get('roll_number', ''), 'Admission No', receipt_data.get('admission_number', '')],
        ["Father's Name", receipt_data.get('father_name', ''), '', ''],
    ]
    student_table = Table(student_data, colWidths=[80, 160, 70, 100])
    student_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (2, 0), (2, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), GRAY),
        ('TEXTCOLOR', (2, 0), (2, -1), GRAY),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(student_table)
    story.append(Spacer(1, 6*mm))

    # Fee details with breakup support
    fee_data = [['Description', 'Amount (₹)']]

    # Fee breakup lines (if provided)
    fee_breakup = receipt_data.get('fee_breakup', [])
    if fee_breakup:
        total_amount = 0
        for item in fee_breakup:
            fee_data.append([item.get('name', ''), f"₹ {item.get('amount', 0):,.0f}"])
            total_amount += item.get('amount', 0)
        fee_data.append(['Total Fee', f"₹ {total_amount:,.0f}"])
    else:
        fee_data.append([receipt_data.get('fee_name', 'Fee'), f"₹ {receipt_data.get('amount_due', 0):,.0f}"])

    if receipt_data.get('discount', 0) > 0:
        fee_data.append(['Discount', f"- ₹ {receipt_data.get('discount', 0):,.0f}"])
    fee_data.append(['Amount Paid', f"₹ {receipt_data.get('amount_paid', 0):,.0f}"])
    if receipt_data.get('balance', 0) > 0:
        fee_data.append(['Balance Due', f"₹ {receipt_data.get('balance', 0):,.0f}"])

    fee_table = Table(fee_data, colWidths=[300, 110])
    fee_styles = [
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]
    # Bold + green for paid row
    paid_row = len(fee_data) - 1 if receipt_data.get('balance', 0) <= 0 else len(fee_data) - 2
    fee_styles.append(('FONTNAME', (0, paid_row), (-1, paid_row), 'Helvetica-Bold'))
    fee_styles.append(('BACKGROUND', (0, paid_row), (-1, paid_row), HexColor('#D1FAE5')))
    fee_table.setStyle(TableStyle(fee_styles))
    story.append(fee_table)
    story.append(Spacer(1, 4*mm))

    # Payment mode
    mode = receipt_data.get('payment_mode', 'Cash').replace('_', ' ').title()
    txn = receipt_data.get('transaction_id', '')
    pay_text = f"<b>Payment Mode:</b> {mode}"
    if txn:
        pay_text += f"  |  <b>Transaction ID:</b> {txn}"
    story.append(Paragraph(pay_text, styles['Normal']))
    story.append(Spacer(1, 8*mm))

    # UPI / Bank details (if configured)
    if receipt_data.get('upi_id'):
        story.append(Paragraph(f"<b>School UPI:</b> {receipt_data['upi_id']}", styles['Normal']))
    if receipt_data.get('bank_details'):
        story.append(Paragraph(f"<b>Bank:</b> {receipt_data['bank_details']}", styles['Normal']))

    story.append(Spacer(1, 10*mm))

    # Signature line — use uploaded signatures if available
    principal_sig = _load_signature_image(receipt_data.get('principal_signature_url'))
    stamp_img = _load_signature_image(receipt_data.get('school_stamp_url'), width=30*mm, height=30*mm)
    sig_data = [
        ['' if not stamp_img else stamp_img, '' if not principal_sig else principal_sig],
        ['_________________________', '_________________________'],
        ['Received By', 'Authorized Signatory'],
    ]
    sig_table = Table(sig_data, colWidths=[200, 200])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 2), (-1, 2), GRAY),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(sig_table)
    story.append(Spacer(1, 6*mm))

    # Footer
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceBefore=2*mm))
    story.append(Paragraph("This is a computer-generated receipt. | Generated by EduFlow School Management", styles['Footer']))

    doc.build(story, onFirstPage=_watermark_callback, onLaterPages=_watermark_callback)
    return buffer.getvalue()


def generate_report_card_pdf(school_name, student_data, exam_results):
    """
    Generate a student report card PDF.
    student_data: {name, class_name, section, roll, admission, father_name}
    exam_results: [{exam_name, subjects: [{name, max, obtained, grade, passed}], total, max, pct, passed}]
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=15*mm, rightMargin=15*mm)
    styles = _get_styles()
    story = []

    # School header
    story.append(Paragraph(school_name, styles['SchoolName']))
    story.append(Spacer(1, 1*mm))
    story.append(Paragraph("STUDENT REPORT CARD", styles['DocTitle']))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=4*mm))

    # Student info
    info = [
        ['Student', student_data.get('name', ''), 'Class', f"{student_data.get('class_name', '')} {student_data.get('section', '')}"],
        ['Roll No', student_data.get('roll', ''), 'Admission No', student_data.get('admission', '')],
        ["Father's Name", student_data.get('father_name', ''), 'Academic Year', student_data.get('academic_year', '')],
    ]
    info_table = Table(info, colWidths=[65, 170, 70, 130])
    info_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), GRAY), ('TEXTCOLOR', (2, 0), (2, -1), GRAY),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'), ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6*mm))

    # Each exam
    for exam in exam_results:
        story.append(Paragraph(f"<b>{exam['exam_name']}</b>", styles['Heading3']))
        story.append(Spacer(1, 2*mm))

        # Build marks table
        header = ['Subject', 'Max Marks', 'Obtained', 'Grade', 'Status']
        rows = [header]
        for s in exam.get('subjects', []):
            obtained = 'AB' if s.get('absent') else str(s.get('obtained', 0))
            status = '—' if s.get('absent') else ('Pass' if s.get('passed') else 'Needs Work')
            rows.append([s.get('name', ''), str(s.get('max', 0)), obtained, s.get('grade', ''), status])

        # Total row
        rows.append(['TOTAL', str(exam.get('max', 0)), str(exam.get('total', 0)),
                      f"{exam.get('pct', 0)}%", 'PASS' if exam.get('passed') else 'NEEDS IMPROVEMENT'])

        marks_table = Table(rows, colWidths=[140, 65, 65, 55, 100])
        marks_styles = [
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY), ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            # Total row
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), LIGHT_GRAY),
        ]
        # Color the status column
        for i in range(1, len(rows) - 1):
            if rows[i][4] == 'Pass':
                marks_styles.append(('TEXTCOLOR', (4, i), (4, i), SUCCESS))
            elif rows[i][4] == 'Needs Work':
                marks_styles.append(('TEXTCOLOR', (4, i), (4, i), DANGER))
        # Final result color
        if exam.get('passed'):
            marks_styles.append(('TEXTCOLOR', (4, -1), (4, -1), SUCCESS))
        else:
            marks_styles.append(('TEXTCOLOR', (4, -1), (4, -1), DANGER))

        marks_table.setStyle(TableStyle(marks_styles))
        story.append(marks_table)
        story.append(Spacer(1, 6*mm))

    # Signature — use uploaded signatures if available
    story.append(Spacer(1, 10*mm))
    teacher_sig = _load_signature_image(student_data.get('class_teacher_signature_url'), width=40*mm, height=16*mm)
    principal_sig = _load_signature_image(student_data.get('principal_signature_url'), width=40*mm, height=16*mm)
    sig = [
        ['' if not teacher_sig else teacher_sig, '' if not principal_sig else principal_sig, ''],
        ['_________________________', '_________________________', '_________________________'],
        ['Class Teacher', 'Principal', 'Parent/Guardian'],
    ]
    sig_table = Table(sig, colWidths=[140, 140, 140])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'BOTTOM'),
        ('FONTSIZE', (0, 0), (-1, -1), 8), ('TEXTCOLOR', (0, 2), (-1, 2), GRAY),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER))
    story.append(Paragraph("Computer generated report card | EduFlow School Management System", styles['Footer']))

    doc.build(story, onFirstPage=_watermark_callback, onLaterPages=_watermark_callback)
    return buffer.getvalue()
