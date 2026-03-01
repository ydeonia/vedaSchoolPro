"""Mega Models — Transport, HR, Payroll, Admission, Homework, Library, Certificates"""
import uuid, enum
from datetime import datetime, timezone, date, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


# ═══════════════════════════════════════════════════════════
# TRANSPORT MODULE
# ═══════════════════════════════════════════════════════════

class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    vehicle_number = Column(String(20), nullable=False)  # KA-01-AB-1234
    vehicle_type = Column(String(50), default="bus")  # bus, van, auto
    capacity = Column(Integer, default=40)
    make_model = Column(String(100), nullable=True)  # Tata Starbus, Force Traveller
    year = Column(Integer, nullable=True)
    # Driver details
    driver_name = Column(String(200), nullable=True)
    driver_phone = Column(String(15), nullable=True)
    driver_license = Column(String(50), nullable=True)
    # Conductor details
    conductor_name = Column(String(200), nullable=True)
    conductor_phone = Column(String(15), nullable=True)
    # Documents
    insurance_number = Column(String(100), nullable=True)
    insurance_expiry = Column(Date, nullable=True)
    fitness_expiry = Column(Date, nullable=True)
    permit_expiry = Column(Date, nullable=True)
    gps_device_id = Column(String(100), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    routes = relationship("TransportRoute", back_populates="vehicle")


class TransportRoute(Base):
    __tablename__ = "transport_routes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    vehicle_id = Column(UUID(as_uuid=True), ForeignKey("vehicles.id"), nullable=True)
    route_name = Column(String(200), nullable=False)  # "Route 1 - Koramangala"
    route_number = Column(String(20), nullable=True)
    driver_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    conductor_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    distance_km = Column(Float, nullable=True)
    monthly_fee = Column(Numeric(10, 2), default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    vehicle = relationship("Vehicle", back_populates="routes")
    stops = relationship("RouteStop", back_populates="route", cascade="all, delete-orphan")


class RouteStop(Base):
    __tablename__ = "route_stops"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    route_id = Column(UUID(as_uuid=True), ForeignKey("transport_routes.id"), nullable=False, index=True)
    stop_name = Column(String(200), nullable=False)
    stop_order = Column(Integer, default=1)
    pickup_time = Column(Time, nullable=True)
    drop_time = Column(Time, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    route = relationship("TransportRoute", back_populates="stops")


class StudentTransport(Base):
    __tablename__ = "student_transport"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    route_id = Column(UUID(as_uuid=True), ForeignKey("transport_routes.id"), nullable=False)
    stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    pickup_stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    drop_stop_id = Column(UUID(as_uuid=True), ForeignKey("route_stops.id"), nullable=True)
    start_date = Column(Date, default=date.today)
    end_date = Column(Date, nullable=True)
    is_active = Column(Boolean, default=True)


# ═══════════════════════════════════════════════════════════
# EMPLOYEE / HR MODULE
# ═══════════════════════════════════════════════════════════

class EmployeeType(str, enum.Enum):
    TEACHING = "teaching"
    NON_TEACHING = "non_teaching"
    ADMIN = "admin"
    SUPPORT = "support"


class Employee(Base):
    __tablename__ = "employees"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)  # link to teacher if teaching staff

    employee_code = Column(String(50), nullable=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    email = Column(String(200), nullable=True)
    phone = Column(String(15), nullable=True)
    employee_type = Column(Enum(EmployeeType), default=EmployeeType.NON_TEACHING)
    designation = Column(String(100), nullable=True)  # Clerk, Accountant, Peon, Driver, Guard, Librarian
    department = Column(String(100), nullable=True)  # Admin, Finance, Transport, Library, Maintenance
    date_of_joining = Column(Date, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    blood_group = Column(String(5), nullable=True)
    photo_url = Column(String(500), nullable=True)
    address = Column(Text, nullable=True)
    city = Column(String(100), nullable=True)
    emergency_contact_name = Column(String(200), nullable=True)
    emergency_contact_phone = Column(String(15), nullable=True)

    # Financial
    bank_name = Column(String(200), nullable=True)
    bank_account = Column(String(50), nullable=True)
    ifsc_code = Column(String(20), nullable=True)
    pan_number = Column(String(20), nullable=True)
    aadhaar_number = Column(String(20), nullable=True)
    uan_number = Column(String(20), nullable=True)  # PF UAN
    basic_salary = Column(Numeric(10, 2), default=0)
    hra = Column(Numeric(10, 2), default=0)
    da = Column(Numeric(10, 2), default=0)
    conveyance = Column(Numeric(10, 2), default=0)
    medical = Column(Numeric(10, 2), default=0)
    special_allowance = Column(Numeric(10, 2), default=0)
    pf_deduction = Column(Numeric(10, 2), default=0)
    esi_deduction = Column(Numeric(10, 2), default=0)
    tds_deduction = Column(Numeric(10, 2), default=0)
    other_deduction = Column(Numeric(10, 2), default=0)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    @property
    def gross_salary(self):
        return float(self.basic_salary or 0) + float(self.hra or 0) + float(self.da or 0) + \
               float(self.conveyance or 0) + float(self.medical or 0) + float(self.special_allowance or 0)

    @property
    def total_deductions(self):
        return float(self.pf_deduction or 0) + float(self.esi_deduction or 0) + \
               float(self.tds_deduction or 0) + float(self.other_deduction or 0)

    @property
    def net_salary(self):
        return self.gross_salary - self.total_deductions


class SalarySlip(Base):
    __tablename__ = "salary_slips"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    employee_id = Column(UUID(as_uuid=True), ForeignKey("employees.id"), nullable=False, index=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    basic_salary = Column(Numeric(10, 2), default=0)
    hra = Column(Numeric(10, 2), default=0)
    da = Column(Numeric(10, 2), default=0)
    conveyance = Column(Numeric(10, 2), default=0)
    medical = Column(Numeric(10, 2), default=0)
    special_allowance = Column(Numeric(10, 2), default=0)
    pf_deduction = Column(Numeric(10, 2), default=0)
    esi_deduction = Column(Numeric(10, 2), default=0)
    tds_deduction = Column(Numeric(10, 2), default=0)
    other_deduction = Column(Numeric(10, 2), default=0)
    days_present = Column(Integer, default=0)
    days_absent = Column(Integer, default=0)
    leave_days = Column(Integer, default=0)
    working_days = Column(Integer, default=26)
    gross_salary = Column(Numeric(10, 2), default=0)
    total_deductions = Column(Numeric(10, 2), default=0)
    net_salary = Column(Numeric(10, 2), default=0)
    status = Column(String(20), default="draft")  # draft, generated, paid
    paid_date = Column(Date, nullable=True)
    payment_mode = Column(String(50), nullable=True)
    transaction_ref = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# ADMISSION MODULE
# ═══════════════════════════════════════════════════════════

class AdmissionStatus(str, enum.Enum):
    ENQUIRY = "enquiry"
    APPLICATION = "application"
    DOCUMENT_PENDING = "document_pending"
    INTERVIEW = "interview"
    APPROVED = "approved"
    ENROLLED = "enrolled"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class Admission(Base):
    __tablename__ = "admissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=True)  # 2025-26

    # Student info
    student_name = Column(String(200), nullable=False)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(String(10), nullable=True)
    blood_group = Column(String(5), nullable=True)
    applying_for_class = Column(String(50), nullable=True)
    previous_school = Column(String(300), nullable=True)

    # Parent info
    father_name = Column(String(200), nullable=True)
    father_phone = Column(String(15), nullable=True)
    father_email = Column(String(200), nullable=True)
    father_occupation = Column(String(200), nullable=True)
    mother_name = Column(String(200), nullable=True)
    mother_phone = Column(String(15), nullable=True)
    address = Column(Text, nullable=True)

    # Process
    status = Column(Enum(AdmissionStatus), default=AdmissionStatus.ENQUIRY, index=True)
    enquiry_date = Column(Date, default=date.today)
    application_date = Column(Date, nullable=True)
    interview_date = Column(Date, nullable=True)
    interview_notes = Column(Text, nullable=True)
    approval_date = Column(Date, nullable=True)
    enrollment_date = Column(Date, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    # Fees
    registration_fee_paid = Column(Boolean, default=False)
    admission_fee_paid = Column(Boolean, default=False)

    # Documents
    birth_certificate = Column(Boolean, default=False)
    transfer_certificate = Column(Boolean, default=False)
    previous_marksheet = Column(Boolean, default=False)
    aadhaar_copy = Column(Boolean, default=False)
    photos = Column(Boolean, default=False)

    # Link to student record after enrollment
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# HOMEWORK / ASSIGNMENTS
# ═══════════════════════════════════════════════════════════

class Homework(Base):
    __tablename__ = "homework"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    attachment_url = Column(String(500), nullable=True)
    assigned_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=False)
    max_marks = Column(Integer, nullable=True)
    is_graded = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HomeworkSubmission(Base):
    __tablename__ = "homework_submissions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    homework_id = Column(UUID(as_uuid=True), ForeignKey("homework.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    content = Column(Text, nullable=True)
    attachment_url = Column(String(500), nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.utcnow())
    marks_obtained = Column(Integer, nullable=True)
    teacher_remarks = Column(Text, nullable=True)
    graded_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="submitted")  # submitted, graded, late, missing


# ═══════════════════════════════════════════════════════════
# LIBRARY MODULE
# ═══════════════════════════════════════════════════════════

class Book(Base):
    __tablename__ = "books"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    author = Column(String(200), nullable=True)
    isbn = Column(String(20), nullable=True)
    publisher = Column(String(200), nullable=True)
    category = Column(String(100), nullable=True)  # Fiction, Science, Math, Reference
    rack_number = Column(String(50), nullable=True)
    total_copies = Column(Integer, default=1)
    available_copies = Column(Integer, default=1)
    price = Column(Numeric(10, 2), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class BookIssue(Base):
    __tablename__ = "book_issues"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    book_id = Column(UUID(as_uuid=True), ForeignKey("books.id"), nullable=False, index=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    borrower_type = Column(String(20), nullable=False)  # student, teacher, employee
    borrower_id = Column(UUID(as_uuid=True), nullable=False)
    borrower_name = Column(String(200), nullable=True)
    issue_date = Column(Date, default=date.today)
    due_date = Column(Date, nullable=False)
    return_date = Column(Date, nullable=True)
    fine_amount = Column(Numeric(10, 2), default=0)
    fine_paid = Column(Boolean, default=False)
    status = Column(String(20), default="issued")  # issued, returned, overdue, lost


# ═══════════════════════════════════════════════════════════
# CERTIFICATE GENERATION
# ═══════════════════════════════════════════════════════════

class CertificateType(str, enum.Enum):
    TRANSFER = "transfer_certificate"
    BONAFIDE = "bonafide_certificate"
    CHARACTER = "character_certificate"
    STUDY = "study_certificate"
    CONDUCT = "conduct_certificate"


class Certificate(Base):
    __tablename__ = "certificates"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    cert_type = Column(Enum(CertificateType), nullable=False)
    certificate_number = Column(String(50), nullable=True)
    issue_date = Column(Date, default=date.today)
    content = Column(Text, nullable=True)  # Custom fields stored as JSON
    reason = Column(String(300), nullable=True)  # Reason for TC
    destination_school = Column(String(300), nullable=True)
    conduct = Column(String(100), default="Good")
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_issued = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# TEACHER REMARKS / STUDENT FEEDBACK SYSTEM
# ═══════════════════════════════════════════════════════════

class RemarkCategory(str, enum.Enum):
    STRENGTH = "strength"
    CONCERN = "concern"
    SUGGESTION = "suggestion"

class RemarkTag(Base):
    """Pre-defined skill tags that teachers can tap to quickly give feedback.
    Subject-specific: 'Algebra weak', 'Grammar excellent', 'Handwriting poor' etc."""
    __tablename__ = "remark_tags"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)  # NULL = global default
    subject_name = Column(String(100), nullable=False)  # 'Mathematics', 'English', 'General'
    tag_text = Column(String(200), nullable=False)       # 'Weak in Algebra'
    category = Column(Enum(RemarkCategory), nullable=False)  # strength/concern/suggestion
    icon = Column(String(10), default="📝")              # emoji for display
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

class StudentRemark(Base):
    """Teacher feedback per student, per subject, per exam (or general).
    Combines quick tags + optional free text."""
    __tablename__ = "student_remarks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)  # NULL = general remark
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=True)        # NULL = anytime remark
    tags = Column(Text, nullable=True)          # JSON array of tag IDs: ["uuid1","uuid2"]
    tag_texts = Column(Text, nullable=True)     # Denormalized: ["Algebra weak","Needs practice"]
    custom_remark = Column(String(500), nullable=True)  # Teacher's own words (optional)
    category = Column(Enum(RemarkCategory), default=RemarkCategory.SUGGESTION)
    is_visible_to_parent = Column(Boolean, default=True)
    is_visible_to_student = Column(Boolean, default=True)
    parent_acknowledged = Column(Boolean, default=False)
    parent_acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# SCHOOL EVENT CALENDAR
# ═══════════════════════════════════════════════════════════

class EventType(str, enum.Enum):
    HOLIDAY = "holiday"
    EXAM = "exam"
    EVENT = "event"
    PTM = "ptm"
    SPORTS = "sports"
    CULTURAL = "cultural"
    DEADLINE = "deadline"
    OTHER = "other"

class SchoolEvent(Base):
    __tablename__ = "school_events"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(Enum(EventType), default=EventType.EVENT)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    is_holiday = Column(Boolean, default=False)
    is_all_day = Column(Boolean, default=True)
    applies_to_classes = Column(Text, nullable=True)
    color = Column(String(7), default="#3B82F6")
    location = Column(String(300), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# LEAVE APPLICATION SYSTEM (Student → Parent → Teacher)
# ═══════════════════════════════════════════════════════════

class LeaveReasonType(str, enum.Enum):
    MEDICAL = "medical"
    FAMILY = "family"
    PERSONAL = "personal"
    RELIGIOUS = "religious"
    EMERGENCY = "emergency"
    OTHER = "other"

class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class StudentLeave(Base):
    __tablename__ = "student_leaves"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    reason_type = Column(Enum(LeaveReasonType), nullable=False)
    reason_text = Column(String(500), nullable=True)
    total_days = Column(Integer, default=1)
    parent_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    parent_comment = Column(String(300), nullable=True)
    parent_approved_at = Column(DateTime, nullable=True)
    parent_approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    teacher_status = Column(Enum(ApprovalStatus), default=ApprovalStatus.PENDING)
    teacher_comment = Column(String(300), nullable=True)
    teacher_approved_at = Column(DateTime, nullable=True)
    teacher_approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    has_exam_conflict = Column(Boolean, default=False)
    conflict_details = Column(String(500), nullable=True)
    has_event_conflict = Column(Boolean, default=False)
    event_conflict_details = Column(String(500), nullable=True)
    applied_by = Column(String(20), default="student")
    is_cancelled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# STUDENT HEALTH RECORD
# ═══════════════════════════════════════════════════════════

class StudentHealth(Base):
    __tablename__ = "student_health"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, unique=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    blood_group = Column(String(5), nullable=True)
    height_cm = Column(Float, nullable=True)
    weight_kg = Column(Float, nullable=True)
    bmi = Column(Float, nullable=True)
    vision_left = Column(String(20), nullable=True)
    vision_right = Column(String(20), nullable=True)
    wears_glasses = Column(Boolean, default=False)
    allergies = Column(Text, nullable=True)
    chronic_conditions = Column(Text, nullable=True)
    medications = Column(Text, nullable=True)
    disabilities = Column(Text, nullable=True)
    vaccinations = Column(Text, nullable=True)
    emergency_contact_1 = Column(String(200), nullable=True)
    emergency_contact_2 = Column(String(200), nullable=True)
    family_doctor = Column(String(200), nullable=True)
    doctor_phone = Column(String(15), nullable=True)
    insurance_id = Column(String(100), nullable=True)
    last_checkup_date = Column(Date, nullable=True)
    checkup_notes = Column(Text, nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# STUDENT ACHIEVEMENTS / AWARDS
# ═══════════════════════════════════════════════════════════

class AchievementCategory(str, enum.Enum):
    ACADEMIC = "academic"
    SPORTS = "sports"
    DISCIPLINE = "discipline"
    ATTENDANCE = "attendance"
    EXTRACURRICULAR = "extracurricular"
    LEADERSHIP = "leadership"
    CREATIVITY = "creativity"
    COMMUNITY = "community"

class StudentAchievement(Base):
    __tablename__ = "student_achievements"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(Enum(AchievementCategory), nullable=False)
    badge_icon = Column(String(10), default="🏆")
    awarded_date = Column(Date, nullable=False)
    awarded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_visible_to_parent = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# DAILY DIARY / TEACHER DAILY REMARKS
# ═══════════════════════════════════════════════════════════

class DiaryEntryType(str, enum.Enum):
    POSITIVE = "positive"
    CONCERN = "concern"
    INFORMATIONAL = "informational"
    HOMEWORK_NOTE = "homework_note"

class DailyDiary(Base):
    __tablename__ = "daily_diary"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    entry_date = Column(Date, nullable=False)
    entry_type = Column(Enum(DiaryEntryType), default=DiaryEntryType.INFORMATIONAL)
    content = Column(Text, nullable=False)
    is_visible_to_parent = Column(Boolean, default=True)
    parent_acknowledged = Column(Boolean, default=False)
    parent_acknowledged_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# BOARD RESULTS TRACKER
# ═══════════════════════════════════════════════════════════

class BoardResult(Base):
    """Track board exam results (CBSE/ICSE/State) — class 10 & 12"""
    __tablename__ = "board_results"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year = Column(String(20), nullable=False)  # "2025-26"
    board = Column(String(20), nullable=False)  # cbse, icse, state
    class_level = Column(String(5), nullable=False)  # "10" or "12"
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    student_name = Column(String(200), nullable=False)  # stored separately for alumni
    roll_number = Column(String(50), nullable=True)
    total_marks = Column(Float, nullable=True)
    max_marks = Column(Float, nullable=True)
    percentage = Column(Float, nullable=True)
    grade = Column(String(10), nullable=True)
    result_status = Column(String(20), default="pass")  # pass, fail, compartment, absent
    subject_wise = Column(JSONB, nullable=True)  # [{"subject":"Math","marks":95,"max":100,"grade":"A1"}]
    rank_in_school = Column(Integer, nullable=True)
    is_distinction = Column(Boolean, default=False)  # 90%+
    is_merit = Column(Boolean, default=False)  # School topper / board merit
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# TEACHER AWARDS / RECOGNITION
# ═══════════════════════════════════════════════════════════

class TeacherAward(Base):
    """Monthly/annual teacher recognition & awards"""
    __tablename__ = "teacher_awards"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False)
    award_type = Column(String(50), nullable=False)  # star_of_month, best_performance, innovation, punctuality, parent_choice
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    month = Column(Integer, nullable=True)  # 1-12
    year = Column(Integer, nullable=False)
    prize_details = Column(String(300), nullable=True)  # "Certificate + ₹2000 voucher"
    nominated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    criteria_data = Column(JSONB, nullable=True)  # auto-calculated metrics
    status = Column(String(20), default="nominated")  # nominated, approved, awarded, rejected
    awarded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    teacher = relationship("Teacher")


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — STUDENT PROMOTION
# ═══════════════════════════════════════════════════════════

class StudentPromotion(Base):
    """Track student promotions/demotions between classes"""
    __tablename__ = "student_promotions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    from_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    to_class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)  # null = TC/Dropout
    from_section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    to_section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)
    academic_year_from = Column(String(20), nullable=False)  # "2024-25"
    academic_year_to = Column(String(20), nullable=False)  # "2025-26"
    action = Column(String(20), default="promoted")  # promoted, detained, tc_issued, dropout
    remarks = Column(Text, nullable=True)
    promoted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    promoted_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — ONLINE QUIZ / MCQ
# ═══════════════════════════════════════════════════════════

class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)
    description = Column(Text, nullable=True)
    time_limit_minutes = Column(Integer, default=30)
    total_marks = Column(Float, default=0)
    pass_marks = Column(Float, default=0)
    is_published = Column(Boolean, default=False)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    show_answers_after = Column(Boolean, default=True)
    shuffle_questions = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True)
    question_text = Column(Text, nullable=False)
    question_type = Column(String(20), default="mcq")  # mcq, true_false, short_answer
    option_a = Column(String(500), nullable=True)
    option_b = Column(String(500), nullable=True)
    option_c = Column(String(500), nullable=True)
    option_d = Column(String(500), nullable=True)
    correct_answer = Column(String(10), nullable=False)  # A, B, C, D, TRUE, FALSE
    marks = Column(Float, default=1)
    explanation = Column(Text, nullable=True)
    order_num = Column(Integer, default=0)

    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    answers = Column(JSONB, nullable=True)  # {"q_id":"A", "q_id":"B"...}
    score = Column(Float, default=0)
    total_marks = Column(Float, default=0)
    percentage = Column(Float, default=0)
    time_taken_seconds = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, default=lambda: datetime.utcnow())
    is_completed = Column(Boolean, default=False)


# ═══════════════════════════════════════════════════════════
# SPRINT 25 — ACCOUNTS (INCOME / EXPENSE)
# ═══════════════════════════════════════════════════════════

class AccountTransaction(Base):
    __tablename__ = "account_transactions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    transaction_type = Column(String(20), nullable=False)  # income, expense
    category = Column(String(100), nullable=False)  # fee_collection, salary, utilities, maintenance, transport, misc
    description = Column(Text, nullable=True)
    amount = Column(Float, nullable=False)
    transaction_date = Column(Date, nullable=False)
    payment_mode = Column(String(30), nullable=True)  # cash, bank, upi, cheque
    reference_number = Column(String(100), nullable=True)
    receipt_url = Column(String(500), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class SmsLog(Base):
    """Track SMS sent via gateway"""
    __tablename__ = "sms_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    phone_number = Column(String(15), nullable=False)
    message = Column(Text, nullable=False)
    sms_type = Column(String(50), nullable=True)  # fee_reminder, attendance_alert, announcement, otp
    status = Column(String(20), default="sent")  # sent, delivered, failed
    provider = Column(String(30), nullable=True)  # msg91, twilio, textlocal
    provider_id = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# FEE WAIVER / DISCOUNT
# ═══════════════════════════════════════════════════════════

class FeeWaiver(Base):
    __tablename__ = "fee_waivers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    waiver_type = Column(String(50), nullable=False)  # scholarship, sibling_discount, staff_ward, merit, financial_aid, rte
    title = Column(String(200), nullable=False)  # "Merit Scholarship 50%"
    discount_type = Column(String(20), default="percentage")  # percentage, fixed
    discount_value = Column(Float, nullable=False)  # 50 (means 50%) or 5000 (fixed)
    applicable_fees = Column(JSONB, nullable=True)  # ["tuition","transport"] or null=all
    valid_from = Column(Date, nullable=True)
    valid_to = Column(Date, nullable=True)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(String(20), default="active")  # active, expired, revoked
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# ATTENDANCE FINE
# ═══════════════════════════════════════════════════════════

class AttendanceFineRule(Base):
    __tablename__ = "attendance_fine_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    rule_name = Column(String(200), nullable=False)  # "Daily absence fine"
    fine_type = Column(String(30), default="per_day")  # per_day, monthly_threshold
    fine_amount = Column(Float, default=50)  # ₹50 per absent day
    threshold_days = Column(Integer, nullable=True)  # null for per_day, or 5 for "after 5 absences"
    applicable_to = Column(String(20), default="all")  # all, class_specific
    applicable_classes = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class AttendanceFine(Base):
    __tablename__ = "attendance_fines"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    rule_id = Column(UUID(as_uuid=True), ForeignKey("attendance_fine_rules.id"), nullable=True)
    month = Column(Integer, nullable=False)
    year = Column(Integer, nullable=False)
    absent_days = Column(Integer, default=0)
    fine_amount = Column(Float, default=0)
    status = Column(String(20), default="pending")  # pending, added_to_fee, waived, paid
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# HOSTEL MANAGEMENT
# ═══════════════════════════════════════════════════════════

class Hostel(Base):
    __tablename__ = "hostels"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)  # "Boys Hostel A"
    hostel_type = Column(String(20), default="boys")  # boys, girls, co-ed
    warden_name = Column(String(200), nullable=True)
    warden_phone = Column(String(15), nullable=True)
    total_rooms = Column(Integer, default=0)
    total_beds = Column(Integer, default=0)
    address = Column(Text, nullable=True)
    monthly_fee = Column(Float, default=0)
    mess_fee = Column(Float, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HostelRoom(Base):
    __tablename__ = "hostel_rooms"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hostel_id = Column(UUID(as_uuid=True), ForeignKey("hostels.id"), nullable=False)
    room_number = Column(String(20), nullable=False)
    floor = Column(String(10), nullable=True)
    room_type = Column(String(20), default="shared")  # single, double, shared, dormitory
    bed_count = Column(Integer, default=4)
    occupied_beds = Column(Integer, default=0)
    status = Column(String(20), default="available")  # available, full, maintenance
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class HostelAllocation(Base):
    __tablename__ = "hostel_allocations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    hostel_id = Column(UUID(as_uuid=True), ForeignKey("hostels.id"), nullable=False)
    room_id = Column(UUID(as_uuid=True), ForeignKey("hostel_rooms.id"), nullable=False)
    bed_number = Column(String(10), nullable=True)
    check_in_date = Column(Date, nullable=True)
    check_out_date = Column(Date, nullable=True)
    emergency_contact = Column(String(200), nullable=True)
    emergency_phone = Column(String(15), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())





# ═══════════════════════════════════════════════════════════
# HOUSE SYSTEM
# ═══════════════════════════════════════════════════════════

class House(Base):
    __tablename__ = "houses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # "Red House", "Blue House"
    color = Column(String(7), default="#DC2626")  # hex color
    tagline = Column(String(300), nullable=True)  # "Courage and Strength"
    logo_url = Column(String(500), nullable=True)
    house_master_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)  # teacher incharge
    points = Column(Integer, default=0)  # house points for competitions
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class StudentHouse(Base):
    """Tag students to houses"""
    __tablename__ = "student_houses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    house_id = Column(UUID(as_uuid=True), ForeignKey("houses.id"), nullable=False)
    academic_year = Column(String(20), nullable=True)  # "2025-26"
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    assigned_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# STUDENT ROLES / POSITIONS
# ═══════════════════════════════════════════════════════════

class StudentRole(Base):
    """Head Boy, Head Girl, House Captain, Class Monitor, etc."""
    __tablename__ = "student_roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    role_type = Column(String(50), nullable=False)  # head_boy, head_girl, house_captain, class_monitor, sports_captain, prefect, vice_captain
    title = Column(String(200), nullable=False)  # "Head Boy", "House Captain - Red House"
    house_id = Column(UUID(as_uuid=True), ForeignKey("houses.id"), nullable=True)  # for house-specific roles
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)  # for class-specific roles
    academic_year = Column(String(20), nullable=True)
    awarded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


# ═══════════════════════════════════════════════════════════
# DIGITAL LIBRARY — Magazines, Textbooks, PDFs
# ═══════════════════════════════════════════════════════════

class DigitalContent(Base):
    """Magazines, Textbooks, Study Material uploaded by admin/teachers"""
    __tablename__ = "digital_contents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    content_type = Column(String(50), nullable=False)  # magazine, textbook, notes, worksheet, circular
    file_url = Column(String(500), nullable=False)
    file_size_kb = Column(Integer, default=0)
    thumbnail_url = Column(String(500), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    visibility = Column(String(30), default="students_parents")  # students_parents, students_only, teachers_only, all
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())


class ContentView(Base):
    """Track who viewed what — drill-down analytics"""
    __tablename__ = "content_views"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_id = Column(UUID(as_uuid=True), ForeignKey("digital_contents.id"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=True)
    viewed_at = Column(DateTime, default=lambda: datetime.utcnow())
    duration_seconds = Column(Integer, default=0)  # how long they viewed
    device = Column(String(100), nullable=True)  # browser/device info