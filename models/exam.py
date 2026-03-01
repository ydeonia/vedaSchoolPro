import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Date, ForeignKey, Integer, Float, Text, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class Exam(Base):
    __tablename__ = "exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    academic_year_id = Column(UUID(as_uuid=True), ForeignKey("academic_years.id"), nullable=False)
    name = Column(String(100), nullable=False)  # "Mid-Term", "Final", "Unit Test 1"
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    is_published = Column(Boolean, default=False)  # results visible to students
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    academic_year = relationship("AcademicYear", back_populates="exams")
    exam_subjects = relationship("ExamSubject", back_populates="exam", cascade="all, delete-orphan")


class ExamSubject(Base):
    __tablename__ = "exam_subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    max_marks = Column(Float, nullable=False, default=100)
    passing_marks = Column(Float, nullable=False, default=33)
    exam_date = Column(Date, nullable=True)
    exam_time = Column(String(50), nullable=True)

    exam = relationship("Exam", back_populates="exam_subjects")
    marks = relationship("Marks", back_populates="exam_subject", cascade="all, delete-orphan")


class Marks(Base):
    __tablename__ = "marks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_subject_id = Column(UUID(as_uuid=True), ForeignKey("exam_subjects.id"), nullable=False, index=True)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.id"), nullable=False, index=True)
    marks_obtained = Column(Float, nullable=True)
    grade = Column(String(5), nullable=True)
    remarks = Column(Text, nullable=True)
    is_absent = Column(Boolean, default=False)
    entered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    exam_subject = relationship("ExamSubject", back_populates="marks")
    student = relationship("Student", back_populates="marks")