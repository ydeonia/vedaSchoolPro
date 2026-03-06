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
    canvas_obj.drawCentredString(0, 0, "VedaSchoolPro Verified")
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
    story.append(Paragraph("This is a computer-generated receipt. | Generated by VedaSchoolPro School Management", styles['Footer']))

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
    story.append(Paragraph("Computer generated report card | VedaSchoolPro School Management System", styles['Footer']))

    doc.build(story, onFirstPage=_watermark_callback, onLaterPages=_watermark_callback)
    return buffer.getvalue()


# ═══════════════════════════════════════════════════════════
# SUBSCRIPTION TAX INVOICE — GST-compliant (India)
# ═══════════════════════════════════════════════════════════

def _number_to_words_inr(amount):
    """Convert amount to Indian Rupees in words."""
    ones = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
            'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
            'Seventeen', 'Eighteen', 'Nineteen']
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']

    def _two_digits(n):
        if n < 20:
            return ones[n]
        return tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')

    def _three_digits(n):
        if n >= 100:
            return ones[n // 100] + ' Hundred' + (' and ' + _two_digits(n % 100) if n % 100 else '')
        return _two_digits(n)

    amt = int(round(float(amount)))
    if amt == 0:
        return "Zero Rupees Only"

    parts = []
    if amt >= 10000000:
        parts.append(_two_digits(amt // 10000000) + ' Crore')
        amt %= 10000000
    if amt >= 100000:
        parts.append(_two_digits(amt // 100000) + ' Lakh')
        amt %= 100000
    if amt >= 1000:
        parts.append(_two_digits(amt // 1000) + ' Thousand')
        amt %= 1000
    if amt > 0:
        parts.append(_three_digits(amt))

    return 'Rupees ' + ' '.join(parts) + ' Only'


def generate_subscription_invoice_pdf(invoice_data):
    """
    Generate a GST-compliant tax invoice PDF for subscription payments.

    invoice_data: {
        invoice_number, invoice_date, due_date,
        supplier_name, supplier_gstin, supplier_address, supplier_state_code,
        buyer_name, buyer_gstin, buyer_address, buyer_state_code,
        line_items: [{description, sac, qty, rate, amount}],
        subtotal, discount_amount, coupon_code,
        taxable_amount, cgst_rate, cgst_amount, sgst_rate, sgst_amount,
        igst_rate, igst_amount, total_tax, total_amount,
        status, notes,
    }
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=18*mm, rightMargin=18*mm)
    styles = _get_styles()
    story = []

    # ── Header: Supplier info ──
    supplier_text = f"<b>{invoice_data.get('supplier_name', 'VedaSchoolPro Technologies Pvt Ltd')}</b>"
    supplier_gstin = invoice_data.get('supplier_gstin', '')
    supplier_address = invoice_data.get('supplier_address', '')
    if supplier_gstin:
        supplier_text += f"<br/><font size='8' color='#4F46E5'>GSTIN: {supplier_gstin}</font>"
    if supplier_address:
        supplier_text += f"<br/><font size='7' color='#6B7280'>{supplier_address}</font>"

    story.append(Paragraph(supplier_text, styles['SchoolName']))
    story.append(Spacer(1, 2*mm))
    story.append(HRFlowable(width="100%", thickness=2, color=PRIMARY, spaceAfter=3*mm))

    # ── TAX INVOICE title ──
    story.append(Paragraph("TAX INVOICE", styles['DocTitle']))
    story.append(Spacer(1, 4*mm))

    # ── Invoice info row ──
    inv_date = invoice_data.get('invoice_date', datetime.now().strftime('%d %b %Y'))
    due_date = invoice_data.get('due_date', '')
    info_data = [
        [Paragraph("<b>Invoice No:</b>", styles['Normal']),
         Paragraph(invoice_data.get('invoice_number', ''), styles['Normal']),
         Paragraph("<b>Date:</b>", styles['Normal']),
         Paragraph(str(inv_date), styles['Normal'])],
    ]
    if due_date:
        info_data.append([
            Paragraph("<b>Due Date:</b>", styles['Normal']),
            Paragraph(str(due_date), styles['Normal']),
            Paragraph("<b>Status:</b>", styles['Normal']),
            Paragraph(invoice_data.get('status', 'Issued').upper(), styles['Normal']),
        ])
    info_table = Table(info_data, colWidths=[70, 140, 55, 140])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6*mm))

    # ── Buyer details ──
    buyer_name = invoice_data.get('buyer_name', '')
    buyer_gstin = invoice_data.get('buyer_gstin', '')
    buyer_address = invoice_data.get('buyer_address', '')
    buyer_state = invoice_data.get('buyer_state_code', '')

    buyer_data = [
        ['Bill To:', buyer_name, '', ''],
        ['GSTIN:', buyer_gstin or 'N/A (Unregistered)', '', ''],
        ['Address:', buyer_address or 'N/A', '', ''],
        ['State Code:', buyer_state or 'N/A', '', ''],
    ]
    buyer_table = Table(buyer_data, colWidths=[65, 340, 0, 0])
    buyer_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (0, -1), GRAY),
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_GRAY),
        ('GRID', (0, 0), (1, -1), 0.5, BORDER),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(buyer_table)
    story.append(Spacer(1, 6*mm))

    # ── Line items table ──
    items_header = ['#', 'Description', 'SAC', 'Qty', 'Rate (Rs.)', 'Amount (Rs.)']
    items_rows = [items_header]

    line_items = invoice_data.get('line_items', [])
    for i, item in enumerate(line_items, 1):
        items_rows.append([
            str(i),
            item.get('description', ''),
            item.get('sac', '998315'),
            str(item.get('qty', 1)),
            f"Rs. {float(item.get('rate', 0)):,.2f}",
            f"Rs. {float(item.get('amount', 0)):,.2f}",
        ])

    items_table = Table(items_rows, colWidths=[25, 200, 55, 30, 75, 80])
    items_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), PRIMARY),
        ('TEXTCOLOR', (0, 0), (-1, 0), white),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 4*mm))

    # ── Tax breakup ──
    subtotal = float(invoice_data.get('subtotal', 0))
    discount = float(invoice_data.get('discount_amount', 0))
    taxable = float(invoice_data.get('taxable_amount', 0))
    cgst_rate = float(invoice_data.get('cgst_rate', 0))
    cgst_amt = float(invoice_data.get('cgst_amount', 0))
    sgst_rate = float(invoice_data.get('sgst_rate', 0))
    sgst_amt = float(invoice_data.get('sgst_amount', 0))
    igst_rate = float(invoice_data.get('igst_rate', 0))
    igst_amt = float(invoice_data.get('igst_amount', 0))
    total_tax = float(invoice_data.get('total_tax', 0))
    total = float(invoice_data.get('total_amount', 0))
    coupon = invoice_data.get('coupon_code', '')

    tax_rows = [['', 'Subtotal', f"Rs. {subtotal:,.2f}"]]
    if discount > 0:
        disc_label = f"Discount ({coupon})" if coupon else "Discount"
        tax_rows.append(['', disc_label, f"- Rs. {discount:,.2f}"])
    tax_rows.append(['', 'Taxable Amount', f"Rs. {taxable:,.2f}"])

    if cgst_amt > 0:
        tax_rows.append(['', f"CGST @ {cgst_rate:.0f}%", f"Rs. {cgst_amt:,.2f}"])
        tax_rows.append(['', f"SGST @ {sgst_rate:.0f}%", f"Rs. {sgst_amt:,.2f}"])
    if igst_amt > 0:
        tax_rows.append(['', f"IGST @ {igst_rate:.0f}%", f"Rs. {igst_amt:,.2f}"])

    tax_rows.append(['', 'Total Tax', f"Rs. {total_tax:,.2f}"])
    tax_rows.append(['', 'TOTAL AMOUNT', f"Rs. {total:,.2f}"])

    tax_table = Table(tax_rows, colWidths=[200, 130, 135])
    tax_styles = [
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (1, -2), (2, -2), 0.5, BORDER),
        # Total row bold + green bg
        ('FONTNAME', (1, -1), (2, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (1, -1), (2, -1), 11),
        ('BACKGROUND', (1, -1), (2, -1), HexColor('#D1FAE5')),
        ('GRID', (1, -1), (2, -1), 0.5, BORDER),
    ]
    tax_table.setStyle(TableStyle(tax_styles))
    story.append(tax_table)
    story.append(Spacer(1, 4*mm))

    # ── Amount in words ──
    words = _number_to_words_inr(total)
    story.append(Paragraph(f"<b>Amount in Words:</b> {words}", styles['Normal']))
    story.append(Spacer(1, 3*mm))

    # ── Notes ──
    notes = invoice_data.get('notes', '')
    if notes:
        story.append(Paragraph(f"<b>Notes:</b> {notes}", styles['Normal']))
        story.append(Spacer(1, 3*mm))

    # ── SAC Code info ──
    story.append(Paragraph(
        "<font size='7' color='#6B7280'>SAC Code 998315 — Information Technology Software Services | "
        "GST Rate: 18% (CGST 9% + SGST 9% for intra-state / IGST 18% for inter-state)</font>",
        styles['Normal']
    ))

    story.append(Spacer(1, 10*mm))

    # ── Signature ──
    sig_data = [
        ['', ''],
        ['_________________________', '_________________________'],
        ['Received By', 'For ' + invoice_data.get('supplier_name', 'VedaSchoolPro Technologies')],
    ]
    sig_table = Table(sig_data, colWidths=[200, 200])
    sig_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('TEXTCOLOR', (0, 2), (-1, 2), GRAY),
    ]))
    story.append(sig_table)

    story.append(Spacer(1, 6*mm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceBefore=2*mm))
    story.append(Paragraph(
        "This is a computer-generated invoice and does not require a physical signature. | Generated by VedaSchoolPro",
        styles['Footer']
    ))

    doc.build(story, onFirstPage=_watermark_callback, onLaterPages=_watermark_callback)
    return buffer.getvalue()
