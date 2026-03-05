import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


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
