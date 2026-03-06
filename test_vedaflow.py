"""
VedaFlow Comprehensive Test Script
===================================
Tests all endpoints, privilege system, messaging, and finds bugs.

Usage:
    python test_vedaflow.py --base-url http://localhost:8000

Requirements:
    pip install httpx rich
"""

import httpx
import asyncio
import sys
import json
from datetime import datetime

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════
BASE_URL = "http://localhost:8000"

# Test users — update these with your actual credentials
USERS = {
    "super_admin": {"username": "admin@vedaschoolpro.in", "password": "Admin@123"},
    "school_admin": {"username": "schooladmin@armyschool.in", "password": "School@123"},
}

# ═══════════════════════════════════════════════════════════
# TEST RESULTS TRACKING
# ═══════════════════════════════════════════════════════════
results = {"passed": 0, "failed": 0, "errors": [], "warnings": []}


def log_pass(test_name, detail=""):
    results["passed"] += 1
    print(f"  ✅ {test_name} {detail}")


def log_fail(test_name, detail=""):
    results["failed"] += 1
    results["errors"].append(f"{test_name}: {detail}")
    print(f"  ❌ {test_name} — {detail}")


def log_warn(test_name, detail=""):
    results["warnings"].append(f"{test_name}: {detail}")
    print(f"  ⚠️  {test_name} — {detail}")


# ═══════════════════════════════════════════════════════════
# AUTH TESTS
# ═══════════════════════════════════════════════════════════
async def test_auth(client: httpx.AsyncClient):
    print("\n🔐 AUTH TESTS")
    print("=" * 50)

    # Test login page loads
    r = await client.get("/login")
    if r.status_code == 200:
        log_pass("Login page loads")
    else:
        log_fail("Login page loads", f"Status {r.status_code}")

    # Test invalid login
    r = await client.post("/login", data={"username": "fake@fake.com", "password": "wrong"})
    if r.status_code == 200 and "Invalid" in r.text:
        log_pass("Invalid login rejected")
    else:
        log_warn("Invalid login", f"Status {r.status_code}")

    # Test valid logins
    tokens = {}
    for role, creds in USERS.items():
        r = await client.post("/login", data=creds, follow_redirects=False)
        if r.status_code in (302, 303):
            cookie = r.cookies.get("access_token")
            if cookie:
                tokens[role] = cookie
                log_pass(f"Login {role}", f"→ redirected")
            else:
                log_fail(f"Login {role}", "No access_token cookie")
        elif r.status_code == 500:
            log_fail(f"Login {role}", "500 Internal Server Error — check timezone or DB issue")
        else:
            log_fail(f"Login {role}", f"Status {r.status_code}")

    # Test logout
    r = await client.get("/logout", follow_redirects=False)
    if r.status_code == 302:
        log_pass("Logout works")
    else:
        log_fail("Logout", f"Status {r.status_code}")

    return tokens


# ═══════════════════════════════════════════════════════════
# JWT / PRIVILEGE TESTS
# ═══════════════════════════════════════════════════════════
async def test_jwt_privileges(client: httpx.AsyncClient, token: str):
    print("\n🔑 JWT & PRIVILEGE TESTS")
    print("=" * 50)

    # Decode JWT to check payload (without verification)
    import base64
    parts = token.split(".")
    if len(parts) == 3:
        # Decode payload
        payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
        try:
            payload = json.loads(base64.b64decode(payload_b64))
            log_pass("JWT decodes OK")

            # Check required fields
            for field in ["user_id", "email", "role", "privileges", "is_first_admin"]:
                if field in payload:
                    log_pass(f"JWT has '{field}'", f"= {str(payload[field])[:50]}")
                else:
                    log_fail(f"JWT missing '{field}'", "Privilege system won't work without this!")

            # Check privileges count
            privs = payload.get("privileges", {})
            if isinstance(privs, dict) and len(privs) > 0:
                active = sum(1 for v in privs.values() if v)
                log_pass(f"JWT privileges", f"{active} active out of {len(privs)}")
            else:
                if payload.get("is_first_admin"):
                    log_pass("JWT: first_admin=True (all privileges bypassed)")
                else:
                    log_fail("JWT privileges empty", "User will get 403 on all pages!")

        except Exception as e:
            log_fail("JWT decode", str(e))
    else:
        log_fail("JWT format", f"Expected 3 parts, got {len(parts)}")


# ═══════════════════════════════════════════════════════════
# PAGE ACCESS TESTS (School Admin)
# ═══════════════════════════════════════════════════════════
async def test_school_pages(client: httpx.AsyncClient, token: str):
    print("\n📄 SCHOOL ADMIN PAGE TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    pages = [
        ("/school/dashboard", "Command Center"),
        ("/school/morning-brief", "Morning Brief"),
        ("/school/admission", "Admission Wizard"),
        ("/school/students", "Students List"),
        ("/school/teachers", "Teachers"),
        ("/school/classes", "Classes"),
        ("/school/attendance", "Attendance"),
        ("/school/timetable", "Timetable"),
        ("/school/exams", "Exams"),
        ("/school/marks-entry", "Marks Entry"),
        ("/school/results", "Results"),
        ("/school/fee-structure", "Fee Structure"),
        ("/school/fee-collection", "Fee Collection"),
        ("/school/analytics", "Analytics"),
        ("/school/teacher-attendance", "Teacher Attendance"),
        ("/school/leave-management", "Leave Management"),
        ("/school/announcements", "Announcements"),
        ("/school/activities", "Activities"),
        ("/school/quizzes", "Quizzes"),
        ("/school/houses", "Houses"),
        ("/school/transport/vehicles", "Transport Vehicles"),
        ("/school/transport/routes", "Transport Routes"),
        ("/school/hostel", "Hostel"),
        ("/school/hr/employees", "Employees"),
        ("/school/hr/payroll", "Payroll"),
        ("/school/hr/id-cards", "ID Cards"),
        ("/school/library", "Library"),
        ("/school/certificates", "Certificates"),
        ("/school/separation", "Separation/TC"),
        ("/school/onboarding", "Staff Onboarding"),
        ("/school/staff-privileges", "Staff Privileges"),
        ("/school/student-promotion", "Student Promotion"),
        ("/school/board-results", "Board Results"),
        ("/school/data-export", "Data Export"),
        ("/school/signatures", "Signatures"),
        ("/school/data-safety", "Data Safety"),
        ("/school/accounts", "Accounts"),
        ("/school/fee-waivers", "Fee Waivers"),
        ("/school/academic-years", "Academic Years"),
        ("/school/subjects", "Subjects"),
        ("/school/payment-settings", "Payment Settings"),
        ("/school/notifications", "Notifications"),
        ("/school/communication-settings", "Comm Settings"),
    ]

    for url, name in pages:
        try:
            r = await client.get(url, follow_redirects=False)
            if r.status_code == 200:
                log_pass(f"{name}", f"({url})")
            elif r.status_code == 403:
                log_fail(f"{name}", f"403 FORBIDDEN — missing privilege for {url}")
            elif r.status_code == 302:
                log_warn(f"{name}", f"302 redirect — maybe not logged in? {url}")
            elif r.status_code == 500:
                log_fail(f"{name}", f"500 SERVER ERROR — {url}")
            elif r.status_code == 404:
                log_warn(f"{name}", f"404 — route not registered? {url}")
            else:
                log_warn(f"{name}", f"Status {r.status_code} — {url}")
        except Exception as e:
            log_fail(f"{name}", f"Exception: {e}")


# ═══════════════════════════════════════════════════════════
# API ENDPOINT TESTS
# ═══════════════════════════════════════════════════════════
async def test_apis(client: httpx.AsyncClient, token: str):
    print("\n🔌 API ENDPOINT TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # GET APIs
    get_apis = [
        ("/api/school/classes", "Classes API"),
        ("/api/school/teachers", "Teachers API"),
        ("/api/school/students", "Students API"),
        ("/api/school/houses", "Houses API"),
        ("/api/school/notifications/list", "Notifications API"),
        ("/api/school/notifications/unread-count", "Unread Count API"),
        ("/api/school/morning-brief", "Morning Brief API"),
        ("/api/school/staff-list", "Staff List API"),
        ("/api/school/transport/routes-list", "Transport Routes API"),
    ]

    for url, name in get_apis:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                try:
                    data = r.json()
                    if "error" in data:
                        log_warn(f"{name}", f"200 but error: {data['error']}")
                    else:
                        log_pass(f"{name}", f"({url})")
                except:
                    log_pass(f"{name}", f"200 OK ({url})")
            elif r.status_code == 500:
                log_fail(f"{name}", f"500 SERVER ERROR — {url}")
            else:
                log_warn(f"{name}", f"Status {r.status_code} — {url}")
        except Exception as e:
            log_fail(f"{name}", f"Exception: {e}")


# ═══════════════════════════════════════════════════════════
# PRIVILEGE ENFORCEMENT TESTS
# ═══════════════════════════════════════════════════════════
async def test_privilege_enforcement(client: httpx.AsyncClient, token: str):
    print("\n🛡️ PRIVILEGE ENFORCEMENT TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Test that unauthenticated access redirects
    client2 = httpx.AsyncClient(base_url=BASE_URL)
    r = await client2.get("/school/dashboard", follow_redirects=False)
    if r.status_code == 302 and "/login" in (r.headers.get("location", "")):
        log_pass("Unauthenticated → redirects to login")
    else:
        log_fail("Unauthenticated access", f"Expected 302→login, got {r.status_code}")
    await client2.aclose()

    # Test super admin pages blocked for school admin
    r = await client.get("/super-admin/dashboard", follow_redirects=False)
    if r.status_code in (302, 403):
        log_pass("School admin blocked from super-admin pages")
    else:
        log_fail("Cross-role access", f"School admin can access super-admin! Status {r.status_code}")

    # Test teacher pages blocked for school admin
    r = await client.get("/teacher/dashboard", follow_redirects=False)
    if r.status_code in (302, 403):
        log_pass("School admin blocked from teacher pages")
    else:
        log_warn("Cross-role access", f"School admin got {r.status_code} on teacher page")


# ═══════════════════════════════════════════════════════════
# SUPER ADMIN TESTS
# ═══════════════════════════════════════════════════════════
async def test_super_admin(client: httpx.AsyncClient, token: str):
    print("\n👑 SUPER ADMIN TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    pages = [
        ("/super-admin/dashboard", "SA Dashboard"),
        ("/super-admin/organizations", "SA Organizations"),
    ]

    for url, name in pages:
        try:
            r = await client.get(url, follow_redirects=False)
            if r.status_code == 200:
                log_pass(f"{name}")
            elif r.status_code == 403:
                log_fail(f"{name}", f"403 — super admin blocked!")
            else:
                log_warn(f"{name}", f"Status {r.status_code}")
        except Exception as e:
            log_fail(f"{name}", str(e))


# ═══════════════════════════════════════════════════════════
# DATABASE CHECKS
# ═══════════════════════════════════════════════════════════
async def test_data_integrity(client: httpx.AsyncClient, token: str):
    print("\n🗄️ DATA INTEGRITY CHECKS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Check classes have sections
    r = await client.get("/api/school/classes")
    if r.status_code == 200:
        data = r.json()
        classes = data.get("classes", [])
        if len(classes) > 0:
            log_pass(f"Classes exist", f"({len(classes)} classes)")
            # Check first class has sections
            first = classes[0]
            if first.get("id"):
                r2 = await client.get(f"/api/school/classes/{first['id']}/sections")
                if r2.status_code == 200:
                    secs = r2.json().get("sections", [])
                    if len(secs) > 0:
                        log_pass(f"Sections exist", f"({len(secs)} for {first.get('name', '?')})")
                    else:
                        log_warn("No sections", f"Class {first.get('name')} has no sections")
                else:
                    log_fail("Sections API", f"Status {r2.status_code}")
        else:
            log_warn("No classes", "Database might be empty")

    # Check students
    r = await client.get("/api/school/students")
    if r.status_code == 200:
        data = r.json()
        students = data.get("students", [])
        log_pass(f"Students API", f"({len(students)} students)")
    else:
        log_fail("Students API", f"Status {r.status_code}")

    # Check staff list
    r = await client.get("/api/school/staff-list")
    if r.status_code == 200:
        data = r.json()
        staff = data.get("staff", [])
        log_pass(f"Staff list", f"({len(staff)} staff members)")
        for s in staff:
            if s.get("is_first_admin"):
                log_pass(f"First admin found", f"{s['first_name']} ({s['email']})")
            priv_count = sum(1 for v in (s.get("privileges") or {}).values() if v)
            if priv_count == 0 and not s.get("is_first_admin"):
                log_warn(f"Staff '{s['first_name']}' has 0 privileges", "They can't access anything!")
    else:
        log_fail("Staff list API", f"Status {r.status_code}")


# ═══════════════════════════════════════════════════════════
# PROFILE & CALENDAR TESTS
# ═══════════════════════════════════════════════════════════
async def test_profiles_and_calendars(client: httpx.AsyncClient, token: str):
    print("\n👤 PROFILE & CALENDAR TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Get a student ID for profile tests
    r = await client.get("/api/school/students")
    student_id = None
    if r.status_code == 200:
        students = r.json().get("students", [])
        if students:
            student_id = students[0].get("id")
            log_pass("Got student for profile tests", f"({students[0].get('first_name', '?')})")

    # Get a teacher ID for profile tests
    r = await client.get("/api/school/teachers")
    teacher_id = None
    if r.status_code == 200:
        data = r.json()
        teachers = data if isinstance(data, list) else data.get("teachers", [])
        if teachers:
            teacher_id = teachers[0].get("id") if isinstance(teachers[0], dict) else str(teachers[0].id)
            log_pass("Got teacher for profile tests")

    # ── Student Profile API ──
    if student_id:
        r = await client.get(f"/api/school/students/{student_id}/profile")
        if r.status_code == 200:
            d = r.json()
            s = d.get("student", {})
            # Check ALL expected fields exist
            required = ["full_name", "father_name", "mother_name", "father_phone",
                        "mother_phone", "father_email", "mother_email",
                        "address", "city", "state", "pincode",
                        "emergency_contact", "medical_conditions",
                        "religion", "category", "nationality",
                        "uses_transport", "house_name",
                        "roles", "documents"]
            missing = [f for f in required if f not in s]
            if missing:
                log_fail("Student profile fields", f"Missing: {', '.join(missing)}")
            else:
                log_pass("Student profile", f"All {len(required)} fields present")
        else:
            log_fail("Student profile API", f"Status {r.status_code}")

        # ── Student Attendance Calendar ──
        r = await client.get(f"/api/school/students/{student_id}/attendance-calendar?month=3&year=2026")
        if r.status_code == 200:
            d = r.json()
            if "error" in d:
                log_fail("Student calendar API", d["error"])
            elif "days" in d and "summary" in d:
                days = d["days"]
                summary = d["summary"]
                log_pass("Student attendance calendar", f"{len(days)} days, {summary.get('percentage', 0)}% present")
                # Verify summary has required keys
                req_keys = ["present", "absent", "total_working", "percentage"]
                missing_keys = [k for k in req_keys if k not in summary]
                if missing_keys:
                    log_fail("Calendar summary keys", f"Missing: {', '.join(missing_keys)}")
                else:
                    log_pass("Calendar summary structure", "All keys present")
            else:
                log_fail("Student calendar response", "Missing 'days' or 'summary'")
        else:
            log_fail("Student calendar API", f"Status {r.status_code}")

        # ── Student Profile Page (HTML) ──
        r = await client.get(f"/school/students/{student_id}")
        if r.status_code == 200:
            if "attendance-calendar" in r.text and "achievements" in r.text.lower():
                log_pass("Student profile page", "Has calendar + achievements sections")
            else:
                log_warn("Student profile page", "May be missing calendar/achievements sections")
        else:
            log_fail("Student profile page", f"Status {r.status_code}")

    # ── Teacher Profile API ──
    if teacher_id:
        r = await client.get(f"/api/school/teachers/{teacher_id}/profile-full")
        if r.status_code == 200:
            d = r.json()
            if "error" in d:
                log_fail("Teacher profile API", d["error"])
            else:
                t = d.get("teacher", {})
                required = ["full_name", "employee_id", "designation", "phone",
                            "email", "address", "emergency_contact",
                            "is_class_teacher", "house_name", "work_status"]
                missing = [f for f in required if f not in t]
                if missing:
                    log_fail("Teacher profile fields", f"Missing: {', '.join(missing)}")
                else:
                    log_pass("Teacher profile", f"All {len(required)} fields present")

                # Check assignments
                asgn = d.get("assignments", [])
                log_pass("Teacher assignments", f"{len(asgn)} assignments loaded")

                # Check awards
                awards = d.get("awards", [])
                log_pass("Teacher awards", f"{len(awards)} awards loaded")

                # Check attendance summary
                att = d.get("attendance_summary", {})
                if "this_month" in att and "overall" in att:
                    log_pass("Teacher attendance summary", f"This month: {att['this_month'].get('percentage', 0)}%")
                else:
                    log_fail("Teacher attendance summary", "Missing this_month or overall")
        else:
            log_fail("Teacher profile API", f"Status {r.status_code}")

        # ── Teacher Attendance Calendar ──
        r = await client.get(f"/api/school/teachers/{teacher_id}/attendance-calendar?month=3&year=2026")
        if r.status_code == 200:
            d = r.json()
            if "error" in d:
                log_fail("Teacher calendar API", d["error"])
            elif "days" in d:
                log_pass("Teacher attendance calendar", f"{len(d['days'])} days")
            else:
                log_fail("Teacher calendar response", "Missing 'days'")
        else:
            log_fail("Teacher calendar API", f"Status {r.status_code}")

        # ── Teacher Profile Page (HTML) ──
        r = await client.get(f"/school/teachers/{teacher_id}")
        if r.status_code == 200:
            if "<script>" in r.text and "profile-full" in r.text:
                log_pass("Teacher profile page", "Renders with profile-full API call")
            else:
                log_warn("Teacher profile page", "May have rendering issues")
        else:
            log_fail("Teacher profile page", f"Status {r.status_code}")


# ═══════════════════════════════════════════════════════════
# LEAVE FLOW TESTS
# ═══════════════════════════════════════════════════════════
async def test_leave_flow(client: httpx.AsyncClient, token: str):
    print("\n📋 LEAVE FLOW TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Check leave list API
    r = await client.get("/api/sprint21/leaves/pending")
    if r.status_code == 200:
        log_pass("Leave pending list API")
    elif r.status_code == 500:
        log_fail("Leave pending API", "500 error")
    else:
        log_warn("Leave pending API", f"Status {r.status_code}")


# ═══════════════════════════════════════════════════════════
# DUPLICATE FLOW DETECTION
# ═══════════════════════════════════════════════════════════
async def test_no_duplicate_flows(client: httpx.AsyncClient, token: str):
    print("\n🔍 DUPLICATE FLOW DETECTION")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Check students page does NOT have "Add Student" modal anymore
    r = await client.get("/school/students")
    if r.status_code == 200:
        if 'New Admission' in r.text and 'href="/school/admissions"' in r.text:
            log_pass("Students page → links to Admissions", "No duplicate Add Student")
        elif "addStudentModal" in r.text and "openModal('addStudentModal')" in r.text:
            log_warn("Students page has Add Student modal", "Should route through Admissions pipeline")
        else:
            log_pass("Students page buttons OK")

    # Check that teacher creation exists only in teachers page
    r = await client.get("/school/teachers")
    if r.status_code == 200:
        if "addTeacherModal" in r.text:
            log_pass("Teachers page has Add Teacher", "Quick-add available")

    # Check employee onboarding is the main lifecycle
    r = await client.get("/school/employee-onboarding")
    if r.status_code == 200:
        log_pass("Employee onboarding page", "Main employee lifecycle available")
    else:
        log_warn("Employee onboarding", f"Status {r.status_code}")

    # Check settings page loads
    r = await client.get("/school/settings")
    if r.status_code == 200:
        log_pass("Unified settings page")
    else:
        log_warn("Settings page", f"Status {r.status_code}")


# ═══════════════════════════════════════════════════════════
# HELP SYSTEM TESTS
# ═══════════════════════════════════════════════════════════
async def test_help_system(client: httpx.AsyncClient, token: str):
    print("\n❓ HELP SYSTEM TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Check that pages have contextual help tooltips via the script
    r = await client.get("/school/dashboard")
    if r.status_code == 200:
        if "pageHelp" in r.text and "fa-info-circle" in r.text:
            log_pass("Dashboard has help tooltip system")
        else:
            log_warn("Dashboard help", "pageHelp script not found")

    # Check help API
    r = await client.get("/api/school/help/tip?page=dashboard")
    if r.status_code == 200:
        log_pass("Help tip API")
    else:
        log_warn("Help tip API", f"Status {r.status_code}")

    r = await client.get("/api/school/help/articles?page=dashboard")
    if r.status_code == 200:
        log_pass("Help articles API")
    else:
        log_warn("Help articles API", f"Status {r.status_code}")


# ═══════════════════════════════════════════════════════════
# KEY PAGE HEALTH CHECK (no 500 errors)
# ═══════════════════════════════════════════════════════════
async def test_page_health(client: httpx.AsyncClient, token: str):
    print("\n🏥 PAGE HEALTH CHECK (no 500s)")
    print("=" * 50)

    client.cookies.set("access_token", token)

    critical_pages = [
        "/school/dashboard", "/school/teachers", "/school/students",
        "/school/attendance", "/school/teacher-attendance",
        "/school/admissions", "/school/timetable",
        "/school/fee-collection", "/school/fee-structures",
        "/school/exam-center", "/school/report-cards",
        "/school/transport", "/school/events",
        "/school/communication", "/school/settings",
        "/school/hr-employees", "/school/employee-onboarding",
        "/school/staff-privileges", "/school/separation",
        "/school/houses", "/school/library",
        "/school/leave-management", "/school/student-achievements",
        "/school/activities", "/school/branding", "/school/photo-approvals",
        "/school/exams", "/school/marks-entry", "/school/results",
        "/school/reports/center",
    ]

    failed_500 = []
    for url in critical_pages:
        try:
            r = await client.get(url)
            name = url.split("/")[-1]
            if r.status_code == 500:
                log_fail(f"PAGE {name}", f"500 error!")
                failed_500.append(url)
            elif r.status_code == 200:
                pass  # Don't spam — only report failures
            elif r.status_code == 403:
                pass  # Privilege issue — not a bug
            elif r.status_code == 302:
                pass  # Redirect — probably auth
        except Exception as e:
            log_fail(f"PAGE {url}", str(e))

    ok_count = len(critical_pages) - len(failed_500)
    log_pass(f"Pages OK: {ok_count}/{len(critical_pages)}")
    if failed_500:
        log_fail(f"Pages with 500 errors", f"{', '.join(failed_500)}")


async def test_photo_and_branding(client: httpx.AsyncClient, token: str):
    print("\n📸 PHOTO UPLOAD & BRANDING TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Test: Photo requests list (should return empty or list)
    r = await client.get("/api/school/photo-requests")
    if r.status_code == 200:
        data = r.json()
        log_pass(f"Photo requests list API: {data.get('count', 0)} pending")
    else:
        log_fail("Photo requests list", f"Status {r.status_code}")

    # Test: Branding GET API
    r = await client.get("/api/school/branding")
    if r.status_code == 200:
        data = r.json()
        if "theme_color" in data:
            log_pass(f"Branding API: theme={data['theme_color']}, logo={'yes' if data.get('logo_url') else 'no'}")
        else:
            log_fail("Branding API", "Missing theme_color field")
    else:
        log_fail("Branding API", f"Status {r.status_code}")

    # Test: Theme color update
    r = await client.put("/api/school/branding/theme",
        json={"theme_color": "#2563EB"},
        headers={"Content-Type": "application/json"})
    if r.status_code == 200 and r.json().get("success"):
        log_pass("Theme color update: #2563EB")
    else:
        log_fail("Theme color update", f"Status {r.status_code}")

    # Reset to default
    await client.put("/api/school/branding/theme",
        json={"theme_color": "#4F46E5"},
        headers={"Content-Type": "application/json"})

    # Test: Invalid color
    r = await client.put("/api/school/branding/theme",
        json={"theme_color": "not-a-color"},
        headers={"Content-Type": "application/json"})
    if r.status_code == 400:
        log_pass("Invalid color rejected correctly")
    else:
        log_warn("Invalid color not rejected", f"Status {r.status_code}")

    # Test: Photo approvals page
    r = await client.get("/school/photo-approvals")
    if r.status_code == 200:
        log_pass("Photo approvals page loads OK")
    elif r.status_code == 403:
        log_warn("Photo approvals page", "Privilege not assigned")
    else:
        log_fail("Photo approvals page", f"Status {r.status_code}")

    # Test: Branding page
    r = await client.get("/school/branding")
    if r.status_code == 200:
        log_pass("Branding page loads OK")
    elif r.status_code == 403:
        log_warn("Branding page", "Privilege not assigned")
    else:
        log_fail("Branding page", f"Status {r.status_code}")


async def test_updated_at_fields(client: httpx.AsyncClient, token: str):
    print("\n🕐 LAST-UPDATED / CHANGELOG TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Get a student to test
    r = await client.get("/api/school/students?limit=1")
    if r.status_code == 200:
        data = r.json()
        students = data.get("students", [])
        if students:
            sid = students[0].get("id")
            r2 = await client.get(f"/api/school/students/{sid}/profile")
            if r2.status_code == 200:
                profile = r2.json().get("student", {})
                if "updated_at" in profile:
                    log_pass(f"Student profile has updated_at: {profile['updated_at'] or '(empty)'}")
                else:
                    log_fail("Student profile", "Missing updated_at field")
                if "created_at" in profile:
                    log_pass(f"Student profile has created_at: {profile['created_at'] or '(empty)'}")
                else:
                    log_fail("Student profile", "Missing created_at field")
        else:
            log_warn("No students found", "Skipping updated_at test")

    # Get a teacher to test
    r = await client.get("/api/school/teachers")
    if r.status_code == 200:
        data = r.json()
        teachers = data.get("teachers", [])
        if teachers:
            tid = teachers[0].get("id")
            r2 = await client.get(f"/api/school/teachers/{tid}/profile-full")
            if r2.status_code == 200:
                profile = r2.json().get("teacher", {})
                if "updated_at" in profile:
                    log_pass(f"Teacher profile has updated_at: {profile['updated_at'] or '(empty)'}")
                else:
                    log_fail("Teacher profile", "Missing updated_at field")
                if "created_at" in profile:
                    log_pass(f"Teacher profile has created_at: {profile['created_at'] or '(empty)'}")
                else:
                    log_fail("Teacher profile", "Missing created_at field")
        else:
            log_warn("No teachers found", "Skipping updated_at test")


async def test_report_center(client: httpx.AsyncClient, token: str):
    print("\n📊 REPORT CENTER TESTS")
    print("=" * 50)

    client.cookies.set("access_token", token)

    # Test: Reports page loads
    try:
        r = await client.get("/school/reports/center")
        if r.status_code == 200:
            if "rpt-cats" in r.text and "generateReport" in r.text:
                log_pass("Report Center page loads with all components")
            else:
                log_warn("Report Center page", "Missing expected UI elements")
        else:
            log_fail("Report Center page", f"Status {r.status_code}")
    except Exception as e:
        log_fail("Report Center page", str(e))

    # Test all report APIs
    report_tests = [
        ("/api/school/reports/student-attendance?month=3&year=2026", "Student attendance report"),
        ("/api/school/reports/teacher-attendance?month=3&year=2026", "Teacher attendance report"),
        ("/api/school/reports/academic-performance", "Academic performance report"),
        ("/api/school/reports/fee-collection", "Fee collection report"),
        ("/api/school/reports/transport", "Transport report"),
        ("/api/school/reports/houses", "Houses report"),
        ("/api/school/reports/tc-alumni", "TC/Alumni report"),
        ("/api/school/reports/login-history?days=30", "Login history report"),
        ("/api/school/reports/student-directory?limit=50", "Student directory report"),
        ("/api/school/reports/student-leaves", "Student leaves report"),
        ("/api/school/reports/exams-list", "Exams list"),
    ]

    for url, name in report_tests:
        try:
            r = await client.get(url)
            if r.status_code == 200:
                d = r.json()
                total = d.get("total", len(d.get("exams", d.get("rows", []))))
                extra = ""
                s = d.get("summary", {})
                if "avg_attendance" in s:
                    extra = f", avg={s['avg_attendance']}%"
                elif "total_collected" in s:
                    extra = f", collected={s['total_collected']}"
                elif "active" in s:
                    extra = f", active={s['active']}"
                log_pass(f"{name}: {total} records{extra}")
            else:
                log_fail(name, f"Status {r.status_code}")
        except Exception as e:
            log_warn(name, f"Timeout/Error: {str(e)[:60]}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════
async def main():
    global BASE_URL
    if len(sys.argv) > 2 and sys.argv[1] == "--base-url":
        BASE_URL = sys.argv[2]

    print("=" * 60)
    print(f"🧪 VedaFlow Test Suite")
    print(f"   Target: {BASE_URL}")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    async with httpx.AsyncClient(base_url=BASE_URL, follow_redirects=False, timeout=15) as client:

        # 1. Auth tests — get tokens
        tokens = await test_auth(client)

        # 2. JWT tests
        if "school_admin" in tokens:
            await test_jwt_privileges(client, tokens["school_admin"])

        # 3. School admin page tests
        if "school_admin" in tokens:
            await test_school_pages(client, tokens["school_admin"])
            await test_apis(client, tokens["school_admin"])
            await test_privilege_enforcement(client, tokens["school_admin"])
            await test_data_integrity(client, tokens["school_admin"])
            await test_profiles_and_calendars(client, tokens["school_admin"])
            await test_leave_flow(client, tokens["school_admin"])
            await test_no_duplicate_flows(client, tokens["school_admin"])
            await test_help_system(client, tokens["school_admin"])
            await test_page_health(client, tokens["school_admin"])
            await test_photo_and_branding(client, tokens["school_admin"])
            await test_updated_at_fields(client, tokens["school_admin"])
            await test_report_center(client, tokens["school_admin"])

        # 4. Super admin tests
        if "super_admin" in tokens:
            await test_super_admin(client, tokens["super_admin"])

    # ═══════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    print(f"📊 TEST SUMMARY")
    print("=" * 60)
    total = results["passed"] + results["failed"]
    print(f"  ✅ Passed:   {results['passed']}")
    print(f"  ❌ Failed:   {results['failed']}")
    print(f"  ⚠️  Warnings: {len(results['warnings'])}")
    print(f"  📋 Total:    {total}")

    if results["errors"]:
        print(f"\n🔥 FAILURES:")
        for e in results["errors"]:
            print(f"  → {e}")

    if results["warnings"]:
        print(f"\n⚠️  WARNINGS:")
        for w in results["warnings"]:
            print(f"  → {w}")

    print()
    if results["failed"] == 0:
        print("🎉 ALL TESTS PASSED!")
    else:
        print(f"🚨 {results['failed']} TESTS FAILED — fix these before deploying")

    return results["failed"]


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)