import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Enum as SAEnum, JSON, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base
import enum


class UserRole(str, enum.Enum):
    """
    Simple role types — determines DASHBOARD LAYOUT, not access.
    Access is controlled by privileges JSON, not by role.
    """
    SUPER_ADMIN = "super_admin"     # Platform owner (you)
    CHAIRMAN = "chairman"           # Trustee/Chairman — org-level oversight across all branches
    SCHOOL_ADMIN = "school_admin"   # Any school staff — principal, clerk, coordinator, accountant
    TEACHER = "teacher"             # Teachers (can also get admin privileges)
    STUDENT = "student"
    PARENT = "parent"


# ═══════════════════════════════════════════════════════════
# PRIVILEGE DEFINITIONS — The 25 checkboxes
# Grouped into: Student, Academic, Finance, HR, Operations, Communication, Reports
# ═══════════════════════════════════════════════════════════

PRIVILEGE_GROUPS = {
    "Student Management": {
        "student_admission": "Student Admission & Profiles",
        "student_attendance": "Student Attendance",
        "student_promotion": "Student Promotion & TC",
        "student_documents": "Student Documents & Records",
    },
    "Academics": {
        "class_management": "Class, Section & Subjects",
        "timetable": "Timetable Management",
        "exam_management": "Exam Creation & Marks Entry",
        "results": "Results & Report Cards",
        "activities": "Activities, Sports & Quiz",
        "online_classes": "Online Classes & Meetings",
    },
    "Finance": {
        "fee_structure": "Fee Structure Setup",
        "fee_collection": "Fee Collection & Receipts",
        "fee_reports": "Fee Reports & Defaulters",
        "salary_payroll": "Salary & Payroll",
        "accounts_expenses": "Accounts & Expenses",
    },
    "HR & Staff": {
        "employee_management": "Employee / Teacher Management",
        "teacher_attendance": "Teacher Attendance & Leave",
        "teacher_performance": "Teacher Performance & Awards",
    },
    "Operations": {
        "transport": "Transport Management",
        "hostel": "Hostel Management",
        "library": "Library",
        "id_cards": "ID Card Generation",
    },
    "Communication": {
        "announcements": "Notifications & Announcements",
        "complaints": "Complaints & Discipline (Tier 2 — Sensitive)",
        "parent_comm": "Parent Communication",
    },
    "Reports & Settings": {
        "analytics": "Analytics Dashboard",
        "reports": "All Reports",
        "school_settings": "School Settings & Configuration",
        "manage_staff": "Manage Staff & Privileges",
    },
}

# Flatten for quick lookup
ALL_PRIVILEGES = {}
for group, privs in PRIVILEGE_GROUPS.items():
    ALL_PRIVILEGES.update(privs)

# When principal creates the first admin account — ALL privileges ON
ALL_PRIVILEGES_ON = {key: True for key in ALL_PRIVILEGES.keys()}

# Privacy Tier 2 — Sensitive privileges (recipient-only within module)
TIER2_SENSITIVE = {"complaints", "teacher_performance", "salary_payroll"}

# Privacy Tier 3 — Private (always recipient-only, no privilege override)
# Messages, escalations, confidential notes — enforced at query level, not here


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=True, index=True)
    phone = Column(String(15), nullable=True, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=True)
    role = Column(SAEnum(UserRole), nullable=False, index=True)
    avatar_url = Column(String(500), nullable=True)

    # Multi-tenant links
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)

    # ═══════════════════════════════════════════════
    # PRIVILEGE SYSTEM — Fedena-style checkboxes
    # ═══════════════════════════════════════════════
    # JSON dict of privilege_key: True/False
    # Example: {"student_admission": true, "fee_collection": true, "complaints": false}
    # For SCHOOL_ADMIN: set during staff creation by principal
    # For TEACHER: optional extra privileges (e.g., exam entry, attendance)
    # For STUDENT/PARENT: not used (fixed dashboard)
    privileges = Column(JSON, nullable=True, default=dict)

    # Is this the first admin of the school? (created by super admin)
    # The first admin has ALL privileges and can manage other staff privileges
    is_first_admin = Column(Boolean, default=False)

    # Staff designation (human-readable title — not a role, just display)
    # "Principal", "Vice Principal", "Clerk", "Accountant", "Coordinator", etc.
    designation = Column(String(100), nullable=True)

    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.utcnow())
    updated_at = Column(DateTime, default=lambda: datetime.utcnow(), onupdate=lambda: datetime.utcnow())

    # Relationships
    organization = relationship("Organization", back_populates="users")
    branch = relationship("Branch", back_populates="users")
    student_profile = relationship("Student", back_populates="user", uselist=False)
    teacher_profile = relationship("Teacher", back_populates="user", uselist=False)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name or ''}".strip()

    def has_privilege(self, privilege_key: str) -> bool:
        """Check if user has a specific privilege."""
        # Super admin has everything
        if self.role == UserRole.SUPER_ADMIN:
            return True
        # First admin of school has everything
        if self.is_first_admin:
            return True
        # Check privilege dict
        if not self.privileges:
            return False
        return self.privileges.get(privilege_key, False)

    def has_any_privilege(self, *privilege_keys: str) -> bool:
        """Check if user has ANY of the given privileges."""
        return any(self.has_privilege(k) for k in privilege_keys)

    def get_active_privileges(self) -> list:
        """Return list of active privilege keys."""
        if self.is_first_admin:
            return list(ALL_PRIVILEGES.keys())
        if not self.privileges:
            return []
        return [k for k, v in self.privileges.items() if v]