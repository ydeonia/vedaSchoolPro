"""ID Card PDF Generator — Student & Employee ID Cards with Signed QR"""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, Frame, PageTemplate
from reportlab.pdfgen import canvas
from io import BytesIO
import os, hashlib, hmac

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

# Secret key for HMAC-signed QR (tamper-proof)
QR_SECRET = os.environ.get("QR_SECRET_KEY", "EduFlow-QR-Secret-2025-X9k$mP")


def _generate_signed_qr(entity_type, entity_id, name=""):
    """
    Generate a tamper-proof QR code image.
    QR contains: EDUFLOW|type|uuid|hmac_hash
    On scan, verify: hmac(secret, "type|uuid") == hash → valid card
    """
    try:
        import qrcode
        payload = f"{entity_type}|{entity_id}"
        sig = hmac.new(QR_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()[:16]
        qr_data = f"EDUFLOW|{payload}|{sig}"

        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        return buf
    except ImportError:
        return None

# Card dimensions (credit card size: 85.6mm x 53.98mm)
CARD_W = 86*mm
CARD_H = 54*mm

# Colors
PRIMARY = HexColor('#4F46E5')
DARK = HexColor('#1E293B')
LIGHT_BG = HexColor('#F8FAFC')
ACCENT = HexColor('#EEF2FF')
WHITE = white
GRAY = HexColor('#64748B')


def _load_image(url, width=20*mm, height=20*mm):
    if not url:
        return None
    filepath = os.path.join(BASE_DIR, url.lstrip('/'))
    if os.path.exists(filepath):
        try:
            return Image(filepath, width=width, height=height)
        except:
            return None
    return None


def generate_student_id_card_pdf(school_data, student_data):
    """
    Generate student ID card PDF (2 cards per page — front + back).
    school_data: {name, logo_url, motto, accreditation, address, phone, landline, website}
    student_data: {name, class_name, roll_number, admission_number, dob, blood_group,
                   photo_url, father_name, mother_name, emergency_contact, address,
                   valid_from, valid_to, student_id}
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # ─── FRONT CARD ────────────────────────────────────
    x_start = (width - CARD_W) / 2
    y_start = height - 40*mm - CARD_H

    # Card border
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(2)
    c.roundRect(x_start, y_start, CARD_W, CARD_H, 4*mm)

    # Top strip (school header)
    c.setFillColor(PRIMARY)
    c.roundRect(x_start, y_start + CARD_H - 16*mm, CARD_W, 16*mm, 4*mm)
    c.rect(x_start, y_start + CARD_H - 16*mm, CARD_W, 8*mm, fill=1)  # Square bottom to overlap rounded

    # School logo
    logo = _load_image(school_data.get('logo_url', ''), width=10*mm, height=10*mm)
    if logo:
        logo.drawOn(c, x_start + 3*mm, y_start + CARD_H - 14*mm)

    # School name on header
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(x_start + 15*mm, y_start + CARD_H - 8*mm, school_data.get('name', 'School')[:35])
    c.setFont('Helvetica', 5)
    motto = school_data.get('motto', '')
    if motto:
        c.drawString(x_start + 15*mm, y_start + CARD_H - 12*mm, motto[:50])
    accred = school_data.get('accreditation', '')
    if accred:
        c.drawString(x_start + 15*mm, y_start + CARD_H - 15*mm, f"Affn: {accred}")

    # STUDENT ID title
    c.setFillColor(PRIMARY)
    c.setFont('Helvetica-Bold', 6)
    c.drawCentredString(x_start + CARD_W/2, y_start + CARD_H - 20*mm, "STUDENT IDENTITY CARD")

    # Photo placeholder
    photo = _load_image(student_data.get('photo_url', ''), width=16*mm, height=20*mm)
    photo_x = x_start + 4*mm
    photo_y = y_start + 6*mm
    if photo:
        photo.drawOn(c, photo_x, photo_y)
    else:
        c.setStrokeColor(GRAY)
        c.setFillColor(LIGHT_BG)
        c.rect(photo_x, photo_y, 16*mm, 20*mm, fill=1)
        c.setFillColor(GRAY)
        c.setFont('Helvetica', 5)
        c.drawCentredString(photo_x + 8*mm, photo_y + 9*mm, "Photo")

    # Student details (right of photo)
    detail_x = x_start + 23*mm
    detail_y = y_start + CARD_H - 24*mm
    line_h = 4.2*mm

    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(detail_x, detail_y, student_data.get('name', '')[:25])
    detail_y -= line_h

    details = [
        ('Class', student_data.get('class_name', '')),
        ('Roll No', str(student_data.get('roll_number', ''))),
        ('Adm No', str(student_data.get('admission_number', ''))),
        ('DOB', str(student_data.get('dob', ''))),
        ('Blood', student_data.get('blood_group', '')),
        ("Father", student_data.get('father_name', '')[:20]),
    ]

    c.setFont('Helvetica', 5.5)
    for label, value in details:
        if value:
            c.setFillColor(GRAY)
            c.drawString(detail_x, detail_y, f"{label}:")
            c.setFillColor(DARK)
            c.drawString(detail_x + 14*mm, detail_y, str(value))
            detail_y -= line_h * 0.85

    # Valid period at bottom
    c.setFont('Helvetica', 4.5)
    c.setFillColor(GRAY)
    valid = f"Valid: {student_data.get('valid_from', '')} to {student_data.get('valid_to', '')}"
    c.drawCentredString(x_start + CARD_W/2, y_start + 2*mm, valid)

    # QR Code (signed, tamper-proof) — top-right of front card
    student_id = student_data.get('student_id', student_data.get('admission_number', 'unknown'))
    qr_buf = _generate_signed_qr("STUDENT", str(student_id), student_data.get('name', ''))
    if qr_buf:
        from reportlab.lib.utils import ImageReader
        qr_img = ImageReader(qr_buf)
        qr_size = 14*mm
        c.drawImage(qr_img, x_start + CARD_W - qr_size - 3*mm, y_start + 8*mm, qr_size, qr_size)
        c.setFont('Helvetica', 3.5)
        c.setFillColor(GRAY)
        c.drawCentredString(x_start + CARD_W - qr_size/2 - 3*mm, y_start + 5.5*mm, "🔒 Verified")

    # ─── BACK CARD ─────────────────────────────────────
    y_back = y_start - 15*mm - CARD_H

    c.setStrokeColor(PRIMARY)
    c.setLineWidth(2)
    c.roundRect(x_start, y_back, CARD_W, CARD_H, 4*mm)

    # Header
    c.setFillColor(PRIMARY)
    c.roundRect(x_start, y_back + CARD_H - 10*mm, CARD_W, 10*mm, 4*mm)
    c.rect(x_start, y_back + CARD_H - 10*mm, CARD_W, 5*mm, fill=1)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(x_start + CARD_W/2, y_back + CARD_H - 7*mm, school_data.get('name', '')[:40])

    # Details on back
    back_y = y_back + CARD_H - 16*mm
    c.setFont('Helvetica', 5.5)

    back_details = [
        ("Student's Address", student_data.get('address', 'N/A')[:60]),
        ("Emergency Contact", student_data.get('emergency_contact', 'N/A')),
        ("Mother's Name", student_data.get('mother_name', 'N/A')[:30]),
    ]

    for label, value in back_details:
        c.setFillColor(GRAY)
        c.drawString(x_start + 5*mm, back_y, f"{label}:")
        c.setFillColor(DARK)
        c.drawString(x_start + 5*mm, back_y - 3.5*mm, str(value))
        back_y -= 8*mm

    # School contact
    c.setFont('Helvetica', 5)
    c.setFillColor(GRAY)
    school_contact = []
    if school_data.get('phone'):
        school_contact.append(f"Ph: {school_data['phone']}")
    if school_data.get('landline'):
        school_contact.append(f"Landline: {school_data['landline']}")
    if school_data.get('website'):
        school_contact.append(school_data['website'])
    contact_str = " | ".join(school_contact)
    c.drawCentredString(x_start + CARD_W/2, y_back + 10*mm, contact_str[:70])

    # School address
    if school_data.get('address'):
        c.drawCentredString(x_start + CARD_W/2, y_back + 6*mm, school_data['address'][:70])

    # Signature line
    c.setStrokeColor(GRAY)
    c.line(x_start + CARD_W - 35*mm, y_back + 3*mm, x_start + CARD_W - 5*mm, y_back + 3*mm)
    c.setFont('Helvetica', 4)
    c.drawCentredString(x_start + CARD_W - 20*mm, y_back + 0.5*mm, "Principal's Signature")

    # "If found" note
    c.setFont('Helvetica-Oblique', 4)
    c.setFillColor(GRAY)
    c.drawString(x_start + 5*mm, y_back + 2*mm, "If found, please return to the school address above.")

    c.save()
    return buffer.getvalue()


def generate_employee_id_card_pdf(school_data, employee_data):
    """
    Generate employee ID card PDF.
    school_data: {name, logo_url, motto, accreditation, address, phone, landline}
    employee_data: {name, employee_code, designation, department, dob, blood_group,
                    photo_url, emergency_contact_name, emergency_contact_phone,
                    address, valid_from, valid_to}
    """
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    x_start = (width - CARD_W) / 2
    y_start = height - 40*mm - CARD_H

    # Card border
    c.setStrokeColor(HexColor('#059669'))  # Green for employees
    c.setLineWidth(2)
    c.roundRect(x_start, y_start, CARD_W, CARD_H, 4*mm)

    # Top strip
    c.setFillColor(HexColor('#059669'))
    c.roundRect(x_start, y_start + CARD_H - 16*mm, CARD_W, 16*mm, 4*mm)
    c.rect(x_start, y_start + CARD_H - 16*mm, CARD_W, 8*mm, fill=1)

    # Logo
    logo = _load_image(school_data.get('logo_url', ''), width=10*mm, height=10*mm)
    if logo:
        logo.drawOn(c, x_start + 3*mm, y_start + CARD_H - 14*mm)

    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(x_start + 15*mm, y_start + CARD_H - 8*mm, school_data.get('name', '')[:35])
    c.setFont('Helvetica', 5)
    if school_data.get('motto'):
        c.drawString(x_start + 15*mm, y_start + CARD_H - 12*mm, school_data['motto'][:50])

    # Title
    c.setFillColor(HexColor('#059669'))
    c.setFont('Helvetica-Bold', 6)
    c.drawCentredString(x_start + CARD_W/2, y_start + CARD_H - 20*mm, "EMPLOYEE IDENTITY CARD")

    # Photo
    photo = _load_image(employee_data.get('photo_url', ''), width=16*mm, height=20*mm)
    photo_x = x_start + 4*mm
    photo_y = y_start + 6*mm
    if photo:
        photo.drawOn(c, photo_x, photo_y)
    else:
        c.setStrokeColor(GRAY)
        c.setFillColor(LIGHT_BG)
        c.rect(photo_x, photo_y, 16*mm, 20*mm, fill=1)
        c.setFillColor(GRAY)
        c.setFont('Helvetica', 5)
        c.drawCentredString(photo_x + 8*mm, photo_y + 9*mm, "Photo")

    # Details
    detail_x = x_start + 23*mm
    detail_y = y_start + CARD_H - 24*mm
    line_h = 4.2*mm

    c.setFillColor(DARK)
    c.setFont('Helvetica-Bold', 8)
    c.drawString(detail_x, detail_y, employee_data.get('name', '')[:25])
    detail_y -= line_h

    details = [
        ('Emp ID', employee_data.get('employee_code', '')),
        ('Desig', employee_data.get('designation', '')),
        ('Dept', employee_data.get('department', '')),
        ('Blood', employee_data.get('blood_group', '')),
        ('DOB', str(employee_data.get('dob', ''))),
    ]

    c.setFont('Helvetica', 5.5)
    for label, value in details:
        if value:
            c.setFillColor(GRAY)
            c.drawString(detail_x, detail_y, f"{label}:")
            c.setFillColor(DARK)
            c.drawString(detail_x + 13*mm, detail_y, str(value)[:25])
            detail_y -= line_h * 0.85

    # Valid
    c.setFont('Helvetica', 4.5)
    c.setFillColor(GRAY)
    valid = f"Valid: {employee_data.get('valid_from', '')} to {employee_data.get('valid_to', '')}"
    c.drawCentredString(x_start + CARD_W/2, y_start + 2*mm, valid)

    # QR Code (signed, tamper-proof)
    emp_id = employee_data.get('employee_id', employee_data.get('employee_code', 'unknown'))
    qr_buf = _generate_signed_qr("EMPLOYEE", str(emp_id), employee_data.get('name', ''))
    if qr_buf:
        from reportlab.lib.utils import ImageReader
        qr_img = ImageReader(qr_buf)
        qr_size = 14*mm
        c.drawImage(qr_img, x_start + CARD_W - qr_size - 3*mm, y_start + 8*mm, qr_size, qr_size)
        c.setFont('Helvetica', 3.5)
        c.setFillColor(GRAY)
        c.drawCentredString(x_start + CARD_W - qr_size/2 - 3*mm, y_start + 5.5*mm, "🔒 Verified")

    # ─── BACK CARD ─────────────────────────────────────
    y_back = y_start - 15*mm - CARD_H
    c.setStrokeColor(HexColor('#059669'))
    c.setLineWidth(2)
    c.roundRect(x_start, y_back, CARD_W, CARD_H, 4*mm)

    c.setFillColor(HexColor('#059669'))
    c.roundRect(x_start, y_back + CARD_H - 10*mm, CARD_W, 10*mm, 4*mm)
    c.rect(x_start, y_back + CARD_H - 10*mm, CARD_W, 5*mm, fill=1)
    c.setFillColor(WHITE)
    c.setFont('Helvetica-Bold', 7)
    c.drawCentredString(x_start + CARD_W/2, y_back + CARD_H - 7*mm, school_data.get('name', '')[:40])

    back_y = y_back + CARD_H - 16*mm
    c.setFont('Helvetica', 5.5)
    back_details = [
        ("Address", employee_data.get('address', 'N/A')[:60]),
        ("Emergency Contact", employee_data.get('emergency_contact_name', 'N/A')),
        ("Emergency Phone", employee_data.get('emergency_contact_phone', 'N/A')),
    ]
    for label, value in back_details:
        c.setFillColor(GRAY)
        c.drawString(x_start + 5*mm, back_y, f"{label}:")
        c.setFillColor(DARK)
        c.drawString(x_start + 5*mm, back_y - 3.5*mm, str(value))
        back_y -= 8*mm

    # School contact
    c.setFont('Helvetica', 5)
    c.setFillColor(GRAY)
    parts = []
    if school_data.get('phone'): parts.append(f"Ph: {school_data['phone']}")
    if school_data.get('landline'): parts.append(f"Landline: {school_data['landline']}")
    c.drawCentredString(x_start + CARD_W/2, y_back + 10*mm, " | ".join(parts)[:70])
    if school_data.get('address'):
        c.drawCentredString(x_start + CARD_W/2, y_back + 6*mm, school_data['address'][:70])

    c.setStrokeColor(GRAY)
    c.line(x_start + CARD_W - 35*mm, y_back + 3*mm, x_start + CARD_W - 5*mm, y_back + 3*mm)
    c.setFont('Helvetica', 4)
    c.drawCentredString(x_start + CARD_W - 20*mm, y_back + 0.5*mm, "Principal's Signature")

    c.save()
    return buffer.getvalue()


def generate_certificate_pdf(school_data, cert_data):
    """
    Generate certificate PDF — TC, Bonafide, Character, Study.
    school_data: {name, logo_url, motto, accreditation, address}
    cert_data: {cert_type, certificate_number, student_name, father_name,
                class_name, dob, admission_number, admission_date, leaving_date,
                reason, conduct, destination_school, issue_date}
    """
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    w, h = A4

    # Border
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(3)
    c.rect(20*mm, 20*mm, w - 40*mm, h - 40*mm)
    c.setLineWidth(1)
    c.rect(22*mm, 22*mm, w - 44*mm, h - 44*mm)

    # Header
    cy = h - 40*mm
    logo = _load_image(school_data.get('logo_url', ''), width=18*mm, height=18*mm)
    if logo:
        logo.drawOn(c, 30*mm, cy - 5*mm)

    c.setFont('Helvetica-Bold', 16)
    c.setFillColor(PRIMARY)
    c.drawCentredString(w/2, cy, school_data.get('name', ''))

    if school_data.get('motto'):
        c.setFont('Helvetica-Oblique', 9)
        c.setFillColor(GRAY)
        c.drawCentredString(w/2, cy - 8*mm, school_data['motto'])

    if school_data.get('accreditation'):
        c.setFont('Helvetica', 8)
        c.drawCentredString(w/2, cy - 14*mm, f"Affiliation No: {school_data['accreditation']}")

    if school_data.get('address'):
        c.setFont('Helvetica', 7)
        c.drawCentredString(w/2, cy - 19*mm, school_data['address'][:80])

    # Divider
    cy -= 25*mm
    c.setStrokeColor(PRIMARY)
    c.setLineWidth(2)
    c.line(30*mm, cy, w - 30*mm, cy)

    # Certificate title
    cy -= 12*mm
    cert_type = cert_data.get('cert_type', 'Certificate')
    titles = {
        'transfer_certificate': 'TRANSFER CERTIFICATE',
        'bonafide_certificate': 'BONAFIDE CERTIFICATE',
        'character_certificate': 'CHARACTER CERTIFICATE',
        'study_certificate': 'STUDY CERTIFICATE',
        'conduct_certificate': 'CONDUCT CERTIFICATE',
    }
    title = titles.get(cert_type, cert_type.replace('_', ' ').upper())

    c.setFont('Helvetica-Bold', 18)
    c.setFillColor(DARK)
    c.drawCentredString(w/2, cy, title)

    # Certificate number
    cy -= 8*mm
    c.setFont('Helvetica', 9)
    c.setFillColor(GRAY)
    c.drawCentredString(w/2, cy, f"Certificate No: {cert_data.get('certificate_number', 'N/A')}")

    # Content
    cy -= 15*mm
    c.setFont('Helvetica', 11)
    c.setFillColor(DARK)

    student = cert_data.get('student_name', '')
    father = cert_data.get('father_name', '')
    class_name = cert_data.get('class_name', '')

    if cert_type == 'transfer_certificate':
        lines = [
            f"This is to certify that {student},",
            f"son/daughter of {father},",
            f"was a bonafide student of this school in Class {class_name}.",
            f"",
            f"Admission Number: {cert_data.get('admission_number', 'N/A')}",
            f"Date of Birth: {cert_data.get('dob', 'N/A')}",
            f"Date of Admission: {cert_data.get('admission_date', 'N/A')}",
            f"Date of Leaving: {cert_data.get('leaving_date', 'N/A')}",
            f"Reason for Leaving: {cert_data.get('reason', 'N/A')}",
            f"Conduct & Character: {cert_data.get('conduct', 'Good')}",
            f"",
            f"He/She is transferred to: {cert_data.get('destination_school', 'N/A')}",
        ]
    elif cert_type == 'bonafide_certificate':
        lines = [
            f"This is to certify that {student},",
            f"son/daughter of {father},",
            f"is a bonafide student of this school.",
            f"",
            f"He/She is currently studying in Class {class_name}.",
            f"Admission Number: {cert_data.get('admission_number', 'N/A')}",
            f"Date of Birth: {cert_data.get('dob', 'N/A')}",
            f"",
            f"This certificate is issued upon request for the purpose",
            f"of {cert_data.get('reason', 'official records')}.",
        ]
    else:
        lines = [
            f"This is to certify that {student},",
            f"son/daughter of {father},",
            f"is/was a student of this school in Class {class_name}.",
            f"",
            f"His/Her conduct and character during the period of study",
            f"has been: {cert_data.get('conduct', 'Good')}.",
        ]

    for line in lines:
        c.drawString(35*mm, cy, line)
        cy -= 7*mm

    # Issue date
    cy -= 10*mm
    c.setFont('Helvetica', 10)
    c.drawString(35*mm, cy, f"Date: {cert_data.get('issue_date', '')}")
    c.drawString(35*mm, cy - 7*mm, f"Place: {school_data.get('address', '').split(',')[0] if school_data.get('address') else ''}")

    # Signatures
    sig_y = 45*mm
    c.setStrokeColor(GRAY)
    c.line(30*mm, sig_y, 70*mm, sig_y)
    c.line(w - 70*mm, sig_y, w - 30*mm, sig_y)
    c.setFont('Helvetica', 8)
    c.setFillColor(GRAY)
    c.drawCentredString(50*mm, sig_y - 4*mm, "Class Teacher")
    c.drawCentredString(w - 50*mm, sig_y - 4*mm, "Principal")

    c.save()
    return buffer.getvalue()


def generate_salary_slip_pdf(school_data, salary_data):
    """
    Generate salary slip PDF.
    school_data: {name, logo_url, address}
    salary_data: {employee_name, employee_code, designation, department, month, year,
                  basic, hra, da, conveyance, medical, special,
                  pf, esi, tds, other_ded, gross, deductions, net,
                  days_present, days_absent, working_days, payment_mode, bank}
    """
    from reportlab.lib.styles import getSampleStyleSheet

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm,
                            leftMargin=20*mm, rightMargin=20*mm)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"<b>{school_data.get('name', '')}</b>", ParagraphStyle('H', fontSize=14, alignment=TA_CENTER, textColor=PRIMARY)))
    if school_data.get('address'):
        story.append(Paragraph(f"<font size='8' color='#6B7280'>{school_data['address']}</font>", ParagraphStyle('A', fontSize=8, alignment=TA_CENTER)))
    story.append(Spacer(1, 3*mm))

    month_names = ['', 'January', 'February', 'March', 'April', 'May', 'June',
                   'July', 'August', 'September', 'October', 'November', 'December']
    m = salary_data.get('month', 1)
    story.append(Paragraph(f"<b>SALARY SLIP — {month_names[m]} {salary_data.get('year', '')}</b>",
                           ParagraphStyle('T', fontSize=12, alignment=TA_CENTER)))
    story.append(Spacer(1, 5*mm))

    # Employee info
    emp_data = [
        ['Employee Name', salary_data.get('employee_name', ''), 'Employee Code', salary_data.get('employee_code', '')],
        ['Designation', salary_data.get('designation', ''), 'Department', salary_data.get('department', '')],
        ['Working Days', str(salary_data.get('working_days', 26)), 'Days Present', str(salary_data.get('days_present', 0))],
    ]
    emp_table = Table(emp_data, colWidths=[80, 140, 80, 110])
    emp_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#E5E7EB')),
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#F8FAFC')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'), ('FONTNAME', (2, 0), (2, -1), 'Helvetica'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'), ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(emp_table)
    story.append(Spacer(1, 5*mm))

    # Earnings vs Deductions (side by side)
    earnings = [
        ['EARNINGS', 'Amount (₹)'],
        ['Basic Salary', f"₹ {salary_data.get('basic', 0):,.0f}"],
        ['HRA', f"₹ {salary_data.get('hra', 0):,.0f}"],
        ['DA', f"₹ {salary_data.get('da', 0):,.0f}"],
        ['Conveyance', f"₹ {salary_data.get('conveyance', 0):,.0f}"],
        ['Medical', f"₹ {salary_data.get('medical', 0):,.0f}"],
        ['Special Allowance', f"₹ {salary_data.get('special', 0):,.0f}"],
        ['Gross Salary', f"₹ {salary_data.get('gross', 0):,.0f}"],
    ]
    deductions = [
        ['DEDUCTIONS', 'Amount (₹)'],
        ['PF', f"₹ {salary_data.get('pf', 0):,.0f}"],
        ['ESI', f"₹ {salary_data.get('esi', 0):,.0f}"],
        ['TDS', f"₹ {salary_data.get('tds', 0):,.0f}"],
        ['Other', f"₹ {salary_data.get('other_ded', 0):,.0f}"],
        ['', ''], ['', ''],
        ['Total Deductions', f"₹ {salary_data.get('deductions', 0):,.0f}"],
    ]

    e_table = Table(earnings, colWidths=[120, 80])
    d_table = Table(deductions, colWidths=[120, 80])
    for t in [e_table, d_table]:
        t.setStyle(TableStyle([
            ('FONTSIZE', (0, 0), (-1, -1), 9), ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#E5E7EB')),
            ('BACKGROUND', (0, 0), (-1, 0), PRIMARY), ('TEXTCOLOR', (0, 0), (-1, 0), white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('BACKGROUND', (0, -1), (-1, -1), HexColor('#EEF2FF')),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))

    combo = Table([[e_table, d_table]], colWidths=[210, 210])
    combo.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP')]))
    story.append(combo)
    story.append(Spacer(1, 5*mm))

    # Net salary
    net_data = [['NET SALARY', f"₹ {salary_data.get('net', 0):,.0f}"]]
    net_table = Table(net_data, colWidths=[300, 110])
    net_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 12), ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, -1), HexColor('#D1FAE5')), ('TEXTCOLOR', (0, 0), (-1, -1), HexColor('#059669')),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
    ]))
    story.append(net_table)
    story.append(Spacer(1, 8*mm))

    # Footer
    story.append(Paragraph("<font size='7' color='#6B7280'>This is a computer-generated salary slip and does not require a signature. | Generated by EduFlow</font>",
                           ParagraphStyle('F', fontSize=7, alignment=TA_CENTER)))

    doc.build(story)
    return buffer.getvalue()