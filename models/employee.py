import uuid
import enum
from datetime import datetime, date
from sqlalchemy import Column, String, Boolean, DateTime, Date, ForeignKey, Text, Integer, Numeric, Enum, Float, Time
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from database import Base


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
