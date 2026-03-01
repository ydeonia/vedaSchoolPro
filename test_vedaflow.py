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
    "super_admin": {"username": "admin@eduflow.in", "password": "Admin@123"},
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