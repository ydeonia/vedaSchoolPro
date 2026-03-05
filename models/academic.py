import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Date, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


class AcademicYear(Base):
    __tablename__ = "academic_years"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    label = Column(String(20), nullable=False)  # "2025-26"
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    branch = relationship("Branch", back_populates="academic_years")
    students = relationship("Student", back_populates="academic_year")
    exams = relationship("Exam", back_populates="academic_year")


class Class(Base):
    __tablename__ = "classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(50), nullable=False)  # "Class 10", "Nursery", "LKG"
    numeric_order = Column(Integer, default=0)  # for sorting
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())

    branch = relationship("Branch", back_populates="classes")
    sections = relationship("Section", back_populates="class_", cascade="all, delete-orphan")
    class_subjects = relationship("ClassSubject", back_populates="class_", cascade="all, delete-orphan")
    students = relationship("Student", back_populates="class_")
    fee_structures = relationship("FeeStructure", back_populates="class_")


class Section(Base):
    __tablename__ = "sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False, index=True)
    name = Column(String(10), nullable=False)  # "A", "B", "C"
    max_students = Column(Integer, default=40)
    is_active = Column(Boolean, default=True)
    class_teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True)

    class_ = relationship("Class", back_populates="sections")
    students = relationship("Student", back_populates="section")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    code = Column(String(20), nullable=True)
    is_optional = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)

    class_subjects = relationship("ClassSubject", back_populates="subject")


class ClassSubject(Base):
    """Maps which subjects are taught in which class, and by which teacher"""
    __tablename__ = "class_subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    teacher_id = Column(UUID(as_uuid=True), ForeignKey("teachers.id"), nullable=True)

    class_ = relationship("Class", back_populates="class_subjects")
    subject = relationship("Subject", back_populates="class_subjects")
    teacher = relationship("Teacher", back_populates="class_subjects")