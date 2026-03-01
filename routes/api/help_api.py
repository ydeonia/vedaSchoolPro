"""In-App Help Center API — GAP 3 from PO Review
Searchable help articles, contextual tips per page, role-specific guidance"""
from fastapi import APIRouter, Request, Query
from models.user import UserRole
from utils.permissions import require_role

router = APIRouter(prefix="/api/school/help")

# ═══ HELP ARTICLES DATABASE ═══
# Each article has a page context, role, and searchable content
HELP_ARTICLES = [
    # ─── ATTENDANCE ───
    {
        "id": "att-1", "page": "attendance", "title": "How does one-tap attendance work?",
        "content": "All students are marked Present by default. Simply tap the red toggle on absent students. This saves time — most classes have 90%+ attendance, so you only mark the exceptions.",
        "roles": ["school_admin", "teacher"], "tags": ["attendance", "present", "absent", "toggle"]
    },
    {
        "id": "att-2", "page": "attendance", "title": "Can I undo a mistake?",
        "content": "Yes! Every attendance action can be undone. Just toggle the student again. Attendance is not locked until end of day. You can edit attendance anytime on the same day.",
        "roles": ["school_admin", "teacher"], "tags": ["attendance", "undo", "mistake", "edit", "fix"]
    },
    {
        "id": "att-3", "page": "attendance", "title": "What if I forget to mark attendance?",
        "content": "Don't worry! The dashboard will show a yellow alert: 'Attendance not marked yet'. You can mark attendance anytime during the day. The system tracks the time of marking for your records.",
        "roles": ["school_admin", "teacher"], "tags": ["attendance", "forget", "reminder", "late"]
    },

    # ─── FEES ───
    {
        "id": "fee-1", "page": "fee-collection", "title": "How do I collect fees?",
        "content": "Select the student, enter the amount, choose payment mode (Cash/UPI/Bank/Card), and click Collect. A watermarked PDF receipt is generated instantly with your school logo and signature.",
        "roles": ["school_admin", "clerk"], "tags": ["fees", "collect", "receipt", "payment", "cash", "upi"]
    },
    {
        "id": "fee-2", "page": "fee-collection", "title": "What if a parent pays partially?",
        "content": "Partial payments are fully supported. The system tracks the remaining balance and marks the fee as 'Partial'. You can collect the balance later — each payment generates its own receipt.",
        "roles": ["school_admin", "clerk"], "tags": ["fees", "partial", "balance", "remaining"]
    },
    {
        "id": "fee-3", "page": "fee-structure", "title": "Can I set different fees for different classes?",
        "content": "Yes! Each fee structure is linked to a specific class. You can create multiple structures with breakups like Tuition, Bus, Lab, Library, etc. Each appears as a line item on the receipt.",
        "roles": ["school_admin"], "tags": ["fees", "structure", "class", "breakup", "tuition"]
    },
    {
        "id": "fee-4", "page": "fee-collection", "title": "What if a payment fails or needs reversal?",
        "content": "You can update the payment status at any time. The audit log records every change. For digital payments, the transaction ID is stored for verification. Nothing is permanent until you confirm.",
        "roles": ["school_admin", "clerk"], "tags": ["fees", "payment", "fail", "reverse", "cancel", "stuck"]
    },

    # ─── EXAMS ───
    {
        "id": "exam-1", "page": "exams", "title": "How do I create an exam?",
        "content": "Go to Exams → Create Exam. Give it a name (e.g., 'Mid-Term'), set dates, then add subjects with max marks. Teachers can then enter marks per student. Results are NOT visible to students until you publish.",
        "roles": ["school_admin"], "tags": ["exam", "create", "marks", "publish"]
    },
    {
        "id": "exam-2", "page": "results", "title": "When do students see their results?",
        "content": "Never automatically! You must click 'Publish' on the exam. Until then, results are draft and only visible to you. This gives you time to verify marks, fix errors, and review before parents see anything.",
        "roles": ["school_admin"], "tags": ["results", "publish", "visible", "students", "parents", "draft"]
    },
    {
        "id": "exam-3", "page": "marks-entry", "title": "Can I change marks after entry?",
        "content": "Yes, until the exam is published. Even after publishing, you can unpublish, edit marks, and republish. All changes are logged in the audit trail for transparency.",
        "roles": ["school_admin"], "tags": ["marks", "edit", "change", "correct", "fix"]
    },

    # ─── TIMETABLE ───
    {
        "id": "tt-1", "page": "timetable", "title": "What if a teacher is double-booked?",
        "content": "The system automatically detects conflicts! If you assign a teacher to two classes at the same time, you'll see a warning. The 'Who is Free?' panel shows available teachers for any period.",
        "roles": ["school_admin"], "tags": ["timetable", "conflict", "double", "free", "available"]
    },

    # ─── TRANSPORT ───
    {
        "id": "trans-1", "page": "transport_vehicles", "title": "How do I track bus routes?",
        "content": "Add your vehicles first (bus number, capacity, driver). Then create routes with stops (with times). Finally, assign students to routes. Transport fees appear as separate line items on fee receipts.",
        "roles": ["school_admin"], "tags": ["transport", "bus", "route", "vehicle", "driver"]
    },

    # ─── HR / PAYROLL ───
    {
        "id": "hr-1", "page": "hr_employees", "title": "Who counts as an employee?",
        "content": "Any non-teaching staff: clerks, accountants, peons, drivers, guards, librarians, wardens, cooks, maintenance, security. Teachers are managed separately in the Teachers module.",
        "roles": ["school_admin"], "tags": ["employee", "staff", "hr", "non-teaching"]
    },
    {
        "id": "hr-2", "page": "hr_payroll", "title": "How does one-click payroll work?",
        "content": "Click 'Generate All Slips' for a month. The system copies each employee's salary structure (Basic + HRA + DA + deductions) and creates individual salary slips. You can download each as a professional PDF.",
        "roles": ["school_admin"], "tags": ["payroll", "salary", "slip", "generate"]
    },

    # ─── CERTIFICATES ───
    {
        "id": "cert-1", "page": "certificates", "title": "What certificates can I generate?",
        "content": "5 types: Transfer Certificate (TC), Bonafide Certificate, Character Certificate, Study Certificate, and Conduct Certificate. Each gets a unique number (CERT-YYYYMMDD-XXXX) and includes school branding.",
        "roles": ["school_admin"], "tags": ["certificate", "tc", "transfer", "bonafide", "character"]
    },

    # ─── DATA & PRIVACY ───
    {
        "id": "data-1", "page": "data-safety", "title": "Can I export all my data?",
        "content": "Yes! Go to Data Hub → Export. You can download CSV files for attendance, fees, results, and student lists. You can also download PDF receipts and report cards. Your data belongs to you — no lock-in.",
        "roles": ["school_admin"], "tags": ["data", "export", "csv", "download", "ownership"]
    },
    {
        "id": "data-2", "page": "data-safety", "title": "Is student data safe?",
        "content": "Student data is isolated by school — no other school can see your data. Each role (teacher, parent, student) only sees what they need. All actions are tracked in audit logs. PDFs are watermarked to prevent tampering.",
        "roles": ["school_admin"], "tags": ["data", "safe", "privacy", "security", "isolated"]
    },

    # ─── COMMUNICATION ───
    {
        "id": "comm-1", "page": "communication_settings", "title": "What are quiet hours?",
        "content": "Quiet hours suppress all notifications during set times (e.g., 9 PM to 7 AM). Parents won't receive SMS/WhatsApp during these hours. This is a respect boundary — no school should wake up parents at midnight.",
        "roles": ["school_admin"], "tags": ["quiet", "hours", "notification", "sms", "whatsapp", "night"]
    },

    # ─── GENERAL ───
    {
        "id": "gen-1", "page": "all", "title": "What does 'trust-first' mean?",
        "content": "EduFlow is designed to reduce anxiety. Every action can be undone, nothing is final until you confirm, data is never deleted without warning, and we tell you 'You can edit this later' everywhere. Schools judge software by how safe it feels.",
        "roles": ["school_admin", "teacher"], "tags": ["trust", "undo", "safe", "philosophy"]
    },
    {
        "id": "gen-2", "page": "all", "title": "Can I use this on my phone?",
        "content": "Yes! EduFlow is fully responsive and works on any phone browser. Teachers can mark attendance from their phone. Parents can check results and fees on mobile. No app download needed.",
        "roles": ["school_admin", "teacher", "student", "parent"], "tags": ["mobile", "phone", "responsive", "app"]
    },
    {
        "id": "gen-3", "page": "all", "title": "What if the internet is slow?",
        "content": "EduFlow is optimized for low-bandwidth. Pages are lightweight (no heavy frameworks). If a save fails due to connectivity, you'll see a clear error with a retry button. Your data isn't lost — just retry when connected.",
        "roles": ["school_admin", "teacher"], "tags": ["internet", "slow", "offline", "bandwidth", "retry"]
    },
]


@router.get("/articles")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_help_articles(request: Request, page: str = "", q: str = ""):
    """Get help articles — filtered by page context or search query"""
    role = request.state.user.get("role", "school_admin")
    results = []

    for a in HELP_ARTICLES:
        # Role filter
        if role not in a["roles"] and "all" not in a.get("page", ""):
            continue
        # Page filter
        if page and a["page"] != page and a["page"] != "all":
            continue
        # Search filter
        if q:
            q_lower = q.lower()
            searchable = f"{a['title']} {a['content']} {' '.join(a['tags'])}".lower()
            if q_lower not in searchable:
                continue
        results.append({"id": a["id"], "title": a["title"], "content": a["content"], "page": a["page"]})

    return {"articles": results, "count": len(results)}


@router.get("/tip")
@require_role(UserRole.SCHOOL_ADMIN)
async def get_contextual_tip(request: Request, page: str = "dashboard"):
    """Get a contextual tip for the current page — shown as a gentle banner"""
    TIPS = {
        "dashboard": {"icon": "💡", "text": "This dashboard refreshes live. Leave it open during school hours to see real-time attendance and fee collection."},
        "attendance": {"icon": "⚡", "text": "Pro tip: All students are pre-marked Present. Just tap the absent ones — saves 90% of the time!"},
        "fee-collection": {"icon": "🧾", "text": "Every receipt gets a watermark and your school logo. Parents can download their own copy from the parent portal."},
        "exams": {"icon": "🔒", "text": "Results stay private until YOU publish them. Take your time verifying marks — no one else can see them yet."},
        "timetable": {"icon": "🔍", "text": "The system auto-detects if a teacher is assigned to two classes at the same time. Try the 'Who is Free?' panel!"},
        "teachers": {"icon": "👩‍🏫", "text": "Teachers can log in with their own accounts to mark attendance, complete periods, and apply for leave."},
        "students": {"icon": "📋", "text": "Student profiles include blood group, address, parent details, and photo. All this appears on their ID card automatically."},
        "analytics": {"icon": "📊", "text": "This dashboard auto-refreshes every 60 seconds. Perfect to keep on the staff room screen during school hours!"},
        "marks-entry": {"icon": "✏️", "text": "You can edit marks anytime before publishing. After publishing, unpublish first, then edit. All changes are logged."},
        "transport_vehicles": {"icon": "🚌", "text": "Add vehicles first, then create routes with stops, then assign students. Transport fees show as a separate line on receipts."},
        "hr_employees": {"icon": "👥", "text": "All staff types — clerks, drivers, guards, cooks — are managed here. Teachers are in the separate Teachers module."},
        "hr_payroll": {"icon": "💰", "text": "One click generates salary slips for ALL employees. Each slip is downloadable as a professional PDF."},
        "certificates": {"icon": "📜", "text": "Certificates get auto-numbered (CERT-YYYYMMDD-XXXX). They include your school logo, motto, and dual signatures."},
        "library": {"icon": "📚", "text": "Late return? The system auto-calculates fine at ₹2/day. You can adjust this rate anytime."},
        "admissions": {"icon": "🎓", "text": "Track every enquiry from first call to enrollment. The status pipeline shows exactly where each applicant stands."},
        "results": {"icon": "📊", "text": "Report cards use CBSE grading (A1-E). No class rankings are shown — we believe in private progress."},
        "communication_settings": {"icon": "🔔", "text": "Quiet hours suppress notifications after school hours. No parent should get an SMS at midnight!"},
        "signatures": {"icon": "🖊️", "text": "Upload your principal signature and school stamp once — they auto-print on every PDF document."},
        "data-safety": {"icon": "🔐", "text": "You own your data. Export everything as CSV or PDF anytime. No lock-in, no hidden fees."},
        "leave-management": {"icon": "📅", "text": "Leave requests appear as pending until you approve. You can see the full leave calendar at a glance."},
    }
    tip = TIPS.get(page, {"icon": "💡", "text": "Need help? Click the ? icon on any page for contextual guidance."})
    return tip
