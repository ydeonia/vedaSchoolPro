import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


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
