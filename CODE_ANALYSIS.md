# VedaFlow (EduFlow) — Codebase Analysis Report

**Date:** March 3, 2026
**Analyzed by:** Claude
**Codebase:** VedaFlow School Management System v1.0.0

---

## 1. Project Overview

VedaFlow (branded as "EduFlow — School Management System") is a **multi-tenant SaaS platform** for Indian K-12 schools, built with Python/FastAPI. It manages the complete school lifecycle — academics, finance, HR, communication, and operations — with role-based dashboards for super admins, chairmen, school administrators, teachers, students, and parents.

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI + Uvicorn |
| ORM | SQLAlchemy 2.0 (async) |
| Database | PostgreSQL (asyncpg driver) |
| Auth | JWT (python-jose) + bcrypt (passlib) |
| Templates | Jinja2 |
| PDF Generation | ReportLab |
| Payments | Razorpay, PhonePe, Paytm (multi-gateway) |
| Notifications | SMS (MSG91/Twilio), WhatsApp (Interakt/Meta), Email (SMTP/Brevo) |
| i18n | Custom engine — 9 Indian languages |

### Scale

| Metric | Count |
|--------|-------|
| Total lines of code | ~49,300 |
| Python source files | 55 |
| HTML templates | 85+ |
| Database models | 50+ tables |
| API endpoints | ~150+ |
| Largest file | `school_admin_api.py` (5,181 lines) |

---

## 2. Architecture

### Multi-Tenancy Model

The system follows an **Organization → Branch → Users** hierarchy. Every data table includes a `branch_id` foreign key for tenant isolation. Organizations can have multiple branches (campuses), each with independent settings for grading, fees, communication, and payment gateways.

### Role System

Six user roles with a **layered access model**:

1. **Role-based** — Determines which dashboard/pages a user sees (SUPER_ADMIN, CHAIRMAN, SCHOOL_ADMIN, TEACHER, STUDENT, PARENT)
2. **Privilege-based** — 25 granular checkbox toggles controlling feature access (e.g., `admission_management`, `fee_collection`, `exam_management`)
3. **Tier-2 Sensitive** — Extra filtering for complaints, teacher performance, and salary data

The `is_first_admin` flag on the first school admin bypasses all privilege checks — a convenience that creates risk.

### Module Inventory

The system covers a wide surface area across 20+ functional modules: academic year/class management, student admissions, attendance (student + teacher), exams and results, fee collection and payments, timetable and period logging, homework and syllabus tracking, messaging and complaints, transport management, HR/payroll, library, hostel, certificates, ID cards, house system, daily diary, board results, teacher remarks, student analytics, school event calendar, online quizzes, accounts (income/expense), fee waivers, and a subscription/billing system.

---

## 3. Strengths

**Comprehensive domain coverage.** The system models the full Indian school management workflow — from admission inquiry through TC issuance — with thoughtful India-specific features like Aadhaar fields, Indian currency formatting (₹ Cr/L/K), board types (CBSE, ICSE, State, IB), and 80G donation receipts.

**Privacy-conscious messaging.** The messaging system implements a 3-tier confidentiality model (General → Complaint → Confidential) with auto-copy rules that default to protecting parents' privacy. Quiet hours (8 PM–7 AM) prevent late-night notifications.

**Multi-gateway payment abstraction.** A clean abstract base class (`PaymentProvider`) supports Razorpay, PhonePe, and Paytm with a factory pattern, making it straightforward to add new gateways.

**Internationalization foundation.** The i18n engine supports 9 languages with Jinja2 integration and per-request language detection via middleware.

**Audit trail.** Most critical actions are logged with user, IP address, and change details.

---

## 4. Critical Issues

### 4.1 Security

**SQL Injection in `chairman_api.py`.** Lines 60 and 66 use Python string interpolation (`.format()`) to build SQL queries with branch IDs. This is a direct injection vector — an attacker with a chairman session could read or modify arbitrary data.

**Plaintext API credentials in database.** Payment gateway keys/secrets (Razorpay, PhonePe, SMTP passwords, WhatsApp tokens) are stored unencrypted in the `PaymentGatewayConfig` and `CommunicationConfig` tables. A database breach would expose all integrated service credentials.

**Aadhaar numbers in plaintext.** Student and parent Aadhaar numbers (India's national ID, equivalent to SSN) are stored as plain strings in the Student model. Indian regulations (UIDAI) require masking and restricted access.

**First-admin privilege bypass.** Users with `is_first_admin=True` completely skip all privilege checks in the `require_privilege` decorator. Combined with the fact that this flag is read from the JWT token without re-verification against the database, this creates a privilege escalation path.

**Missing CSRF protection.** The login form has no CSRF token validation. FastAPI doesn't include CSRF middleware by default, and none has been added.

**`.gitignore` doesn't exclude `.env`.** The gitignore file excludes `venv/` and `.env/` (as a directory), but not the `.env` file itself. If committed, database credentials, the JWT secret key, and super admin password would be in git history.

### 4.2 Data Integrity

**Missing unique constraints.** Several important pairs lack database-level uniqueness: (branch_id, admission_number) on students, (exam_id, subject_id, class_id) on exam subjects, and (branch_id, class_name) for classes. Duplicates can be created at the application level.

**String fields where enums belong.** Teacher `work_status`, activity `status`, donation `status`, and period log `status` are plain strings with no database-level validation. Typos or inconsistent values can slip in.

**Denormalized counts without sync.** `HostelRoom.occupied_beds`, `Book.available_copies`, and subscription usage counts (`current_student_count`) are stored directly but not automatically updated when related records change. They can drift out of sync.

### 4.3 Performance

**N+1 query patterns.** Transport routes (line 39–44), student analytics, parent API, and messaging all loop through records and execute additional queries per item. With large datasets this will degrade significantly.

**No pagination.** Most list endpoints load all records — super admin organization lists, student lists, audit logs (limited to 200 but could be much more), and announcement feeds have no cursor or offset pagination.

**No caching.** Analytics endpoints recalculate complex aggregates on every request. Timezone lookups query the database per request. School settings are re-fetched on every page load.

**Synchronous I/O in async context.** PDF generation loads images from disk synchronously, blocking the event loop. The payment module creates a new `httpx.AsyncClient` per request instead of reusing a connection pool.

### 4.4 Code Quality

**5,000-line mega file.** `school_admin_api.py` at 5,181 lines handles dozens of unrelated endpoints. It should be split into focused modules (academic API, fee API, student API, etc.).

**Duplicate code.** `id_card_generator.py` and `student_id_generator.py` contain nearly identical logic for generating student login IDs. They should be consolidated.

**Bare except clauses.** `auth.py` routes have bare `except:` blocks (lines 80, 118, 180) that silently swallow all errors, making debugging extremely difficult.

**Duplicate router registration.** In `main.py`, `parent_api_router` is imported twice (lines 25 and 27) and registered twice (lines 110 and 112).

**`mega_modules.py` is a monolith.** At 933 lines, this single file defines 20+ models across transport, HR, admissions, library, certificates, homework, quizzes, hostel, and more. Each domain should have its own model file.

---

## 5. Recommendations

### Immediate (Security)

1. **Parameterize all SQL queries** — Replace string interpolation in `chairman_api.py` with SQLAlchemy parameterized queries.
2. **Encrypt sensitive config at rest** — Use Fernet or similar encryption for payment gateway secrets and communication credentials stored in the database.
3. **Add `.env` to `.gitignore`** and rotate any secrets that may have been committed.
4. **Re-verify `is_first_admin` from database** in the privilege decorator rather than trusting the JWT payload.
5. **Mask/encrypt Aadhaar numbers** — Store only last 4 digits in plaintext; encrypt the full number.

### Short-term (Stability)

6. **Add pagination** to all list endpoints (cursor-based for large tables).
7. **Fix N+1 queries** using SQLAlchemy `selectinload()` / `joinedload()` for eager loading.
8. **Replace bare excepts** with specific exception types and proper logging.
9. **Split `school_admin_api.py`** into domain-specific API modules.
10. **Add database-level unique constraints** for critical pairs (admission numbers, exam subjects, etc.).

### Medium-term (Quality)

11. **Add request validation** using Pydantic models for all API inputs.
12. **Implement caching** (Redis or in-memory) for settings, analytics, and timezone lookups.
13. **Consolidate duplicate files** (`id_card_generator.py` + `student_id_generator.py`).
14. **Use enum types** instead of strings for all status fields.
15. **Fix i18n middleware** — currently detects language but doesn't pass it to Jinja2 templates.
16. **Add CSRF middleware** for all state-changing form submissions.
17. **Reuse HTTP clients** — create a shared `httpx.AsyncClient` with connection pooling for payment and notification calls.

---

## 6. File Map

### Top-Level
| File | Lines | Purpose |
|------|-------|---------|
| `main.py` | 129 | FastAPI app setup, router registration, startup |
| `config.py` | 45 | Environment configuration (Settings class) |
| `database.py` | 28 | SQLAlchemy async engine, session factory, Base |
| `requirements.txt` | 22 | Python dependencies |
| `test_vedaflow.py` | 438 | End-to-end test suite |
| `seed_events.py` | 108 | Indian school calendar seeder (43 events) |
| `seed_remark_tags.py` | 209 | Teacher feedback tag seeder (165 tags) |

### Models (23 files, ~2,800 lines)
Core domain models using SQLAlchemy ORM with UUID primary keys. Key models: User, Organization, Branch (+Settings, PaymentConfig, CommConfig), Student (+Documents), Teacher, AcademicYear, Class, Section, Subject, Attendance, Exam (+Marks), Fee (+Records), Notification (+Announcement), Messaging (+Complaints), Subscription (+Plans), Timetable, and 20+ models in `mega_modules.py`.

### Routes (10 page routers + 19 API routers, ~15,000 lines)
Page routers serve Jinja2 templates for each role's dashboard. API routers handle data operations. Largest: `school_admin_api.py` (5,181 lines), `mobile_api_final.py` (1,679 lines).

### Utilities (12 files, ~2,500 lines)
Auth (JWT/bcrypt), audit logging, helpers (Indian formatting), i18n (9 languages), ID card generation, notifications (multi-channel), payments (multi-gateway), PDF generation (receipts/report cards), permissions (RBAC + privileges), timezone management, auto-attendance.

### Templates (85+ HTML files)
Jinja2 templates organized by role: `school_admin/` (45 pages), `student/` (22 pages), `teacher/` (15 pages), `parent/` (6 pages), `super_admin/` (12 pages), `chairman/` (1 page), `payment/` (4 pages).

### Static Assets
CSS (`style.css`), JS (`app.js`), and language files for 8 Indian languages (Assamese, Gujarati, Hindi, Malayalam, Punjabi, Tamil, Telugu) plus English.
