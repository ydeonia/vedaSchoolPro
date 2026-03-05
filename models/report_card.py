"""
Report Card Management System — Database Models
8 new tables for the complete marks lifecycle, audit trail, and PDF generation.
"""
import uuid
import enum
from datetime import datetime, date
from sqlalchemy import (
    Column, String, DateTime, Date, ForeignKey, Integer, Float,
    Text, Boolean, UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


# ═══════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════

class ExamCycleStatus(str, enum.Enum):
    OPEN = "open"
    VERIFICATION_PENDING = "verification_pending"
    LOCKED = "locked"
    PUBLISHED = "published"
    REOPENED = "reopened"


class UploadStatus(str, enum.Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


class SpecialCode(str, enum.Enum):
    AB = "AB"       # Absent
    ML = "ML"       # Medical Leave
    NA = "NA"       # Not Applicable
    EX = "EX"       # Exempted


class ResultStatus(str, enum.Enum):
    PROMOTED = "promoted"
    COMPARTMENT = "compartment"
    DETAINED = "detained"
    NEEDS_IMPROVEMENT = "needs_improvement"


class AuditAction(str, enum.Enum):
    UPLOAD = "upload"
    EDIT = "edit"
    GRACE = "grace"
    BULK = "bulk"
    REOPEN = "reopen"
    DELETE = "delete"
    SUBMIT = "submit"
    LOCK = "lock"
    PUBLISH = "publish"


# ═══════════════════════════════════════════════════════════
# 1. REPORT CARD TEMPLATE — Visual editor layout (like ID card)
# ═══════════════════════════════════════════════════════════

class ReportCardTemplate(Base):
    __tablename__ = "report_card_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)           # "Standard Report Card", "CBSE Format"
    layout_json = Column(JSONB, nullable=True)            # Full visual layout config
    page_size = Column(String(10), default="A4")          # A4, Letter
    orientation = Column(String(15), default="portrait")  # portrait, landscape
    header_config = Column(JSONB, nullable=True)          # School logo, name, address placement
    footer_config = Column(JSONB, nullable=True)          # Signatures, stamp placement
    grading_scale = Column(JSONB, nullable=True)          # Custom grade cutoffs
    show_rank = Column(Boolean, default=True)
    show_attendance = Column(Boolean, default=True)
    show_remarks = Column(Boolean, default=True)
    show_grade = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    exam_cycles = relationship("ExamCycle", back_populates="template")


# ═══════════════════════════════════════════════════════════
# 2. EXAM GROUP — Term grouping (Term 1 = UT1 + Mid-Term)
# ═══════════════════════════════════════════════════════════

class ExamGroup(Base):
    __tablename__ = "exam_groups"
    __table_args__ = (
        UniqueConstraint("branch_id", "academic_year_id", "name", name="uq_exam_group_name"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    name = Column(String(100), nullable=False)          # "Term 1", "Term 2", "Annual"
    display_order = Column(Integer, default=1)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    exam_cycles = relationship("ExamCycle", back_populates="exam_group")


# ═══════════════════════════════════════════════════════════
# 3. EXAM CYCLE — The core entity tying exam to class/deadline
# ═══════════════════════════════════════════════════════════

class ExamCycle(Base):
    __tablename__ = "exam_cycles"
    __table_args__ = (
        Index("ix_exam_cycle_branch_status", "branch_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    exam_group_id = Column(UUID(as_uuid=True), ForeignKey("exam_groups.id"), nullable=True)
    name = Column(String(100), nullable=False)           # "Mid-Term 2026", "Unit Test 1"
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    section_id = Column(UUID(as_uuid=True), ForeignKey("sections.id"), nullable=True)  # null = all sections
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    marks_deadline = Column(Date, nullable=True)         # Teachers must upload before this
    result_date = Column(Date, nullable=True)            # Announcement date
    weightage_percent = Column(Float, default=100)       # Weight in term aggregation
    max_marks_default = Column(Float, default=100)       # Default max marks for subjects
    passing_marks_default = Column(Float, default=33)    # Default passing marks
    template_id = Column(UUID(as_uuid=True), ForeignKey("report_card_templates.id"), nullable=True)
    status = Column(String(25), default=ExamCycleStatus.OPEN.value, nullable=False)
    rank_scope = Column(String(15), default="section")   # section / class
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())
    published_at = Column(DateTime, nullable=True)
    published_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    exam_group = relationship("ExamGroup", back_populates="exam_cycles")
    template = relationship("ReportCardTemplate", back_populates="exam_cycles")
    upload_trackers = relationship("MarksUploadTracker", back_populates="exam_cycle", cascade="all, delete-orphan")
    student_marks = relationship("StudentMarks", back_populates="exam_cycle", cascade="all, delete-orphan")
    student_results = relationship("StudentResult", back_populates="exam_cycle", cascade="all, delete-orphan")


# ═══════════════════════════════════════════════════════════
# 4. MARKS UPLOAD TRACKER — Per teacher per subject status
# ═══════════════════════════════════════════════════════════

class MarksUploadTracker(Base):
    __tablename__ = "marks_upload_trackers"
    __table_args__ = (
        UniqueConstraint("exam_cycle_id", "teacher_id", "subject_id", name="uq_tracker_cycle_teacher_subject"),
        Index("ix_tracker_status", "exam_cycle_id", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_cycle_id = Column(UUID(as_uuid=True), ForeignKey("exam_cycles.id"), nullable=False, index=True)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    status = Column(String(15), default=UploadStatus.DRAFT.value, nullable=False)
    uploaded_at = Column(DateTime, nullable=True)
    submitted_at = Column(DateTime, nullable=True)
    file_name = Column(String(255), nullable=True)
    row_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    exam_cycle = relationship("ExamCycle", back_populates="upload_trackers")


# ═══════════════════════════════════════════════════════════
# 5. STUDENT MARKS — Rich marks with special codes & grace
# ═══════════════════════════════════════════════════════════

class StudentMarks(Base):
    __tablename__ = "student_marks"
    __table_args__ = (
        UniqueConstraint("exam_cycle_id", "student_id", "subject_id", "is_retest", name="uq_student_marks_unique"),
        Index("ix_student_marks_cycle_subject", "exam_cycle_id", "subject_id"),
        Index("ix_student_marks_student", "student_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_cycle_id = Column(UUID(as_uuid=True), ForeignKey("exam_cycles.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)
    marks_obtained = Column(Float, nullable=True)        # null when special_code set
    max_marks = Column(Float, nullable=False, default=100)
    special_code = Column(String(5), nullable=True)      # AB, ML, NA, EX
    grace_marks = Column(Float, default=0)
    final_marks = Column(Float, nullable=True)           # marks_obtained + grace_marks
    grade = Column(String(5), nullable=True)
    remarks = Column(Text, nullable=True)
    is_retest = Column(Boolean, default=False)
    original_mark_id = Column(UUID(as_uuid=True), ForeignKey("student_marks.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    exam_cycle = relationship("ExamCycle", back_populates="student_marks")


# ═══════════════════════════════════════════════════════════
# 6. STUDENT RESULT — Aggregated per student per exam cycle
# ═══════════════════════════════════════════════════════════

class StudentResult(Base):
    __tablename__ = "student_results"
    __table_args__ = (
        UniqueConstraint("exam_cycle_id", "student_id", name="uq_student_result"),
        Index("ix_student_result_cycle", "exam_cycle_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_cycle_id = Column(UUID(as_uuid=True), ForeignKey("exam_cycles.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    total_marks = Column(Float, default=0)
    max_total = Column(Float, default=0)
    percentage = Column(Float, default=0)
    grade = Column(String(5), nullable=True)
    rank = Column(Integer, nullable=True)
    result_status = Column(String(20), default=ResultStatus.PROMOTED.value)
    class_teacher_remarks = Column(Text, nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    exam_cycle = relationship("ExamCycle", back_populates="student_results")


# ═══════════════════════════════════════════════════════════
# 7. MARKS AUDIT LOG — Every change tracked
# ═══════════════════════════════════════════════════════════

class MarksAuditLog(Base):
    __tablename__ = "marks_audit_logs"
    __table_args__ = (
        Index("ix_audit_cycle", "exam_cycle_id"),
        Index("ix_audit_student_marks", "student_marks_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_marks_id = Column(UUID(as_uuid=True), ForeignKey("student_marks.id"), nullable=True)
    exam_cycle_id = Column(UUID(as_uuid=True), ForeignKey("exam_cycles.id"), nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    changed_at = Column(DateTime, default=lambda: datetime.utcnow())
    field_name = Column(String(50), nullable=True)       # marks_obtained, grace_marks, etc.
    old_value = Column(String(100), nullable=True)
    new_value = Column(String(100), nullable=True)
    action = Column(String(20), nullable=False)          # upload, edit, grace, bulk, reopen
    ip_address = Column(String(50), nullable=True)
    reason = Column(Text, nullable=True)


# ═══════════════════════════════════════════════════════════
# 8. REPORT CARD PDF — Generated PDFs per student
# ═══════════════════════════════════════════════════════════

class ReportCardPDF(Base):
    __tablename__ = "report_card_pdfs"
    __table_args__ = (
        Index("ix_rc_pdf_student_cycle", "student_id", "exam_cycle_id"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False)
    exam_cycle_id = Column(UUID(as_uuid=True), ForeignKey("exam_cycles.id"), nullable=False)
    pdf_path = Column(String(500), nullable=True)
    generated_at = Column(DateTime, default=lambda: datetime.utcnow())
    is_latest = Column(Boolean, default=True)
