"""VedaFlow Models — All database models imported for convenience."""
from models.user import User, UserRole
from models.organization import Organization
from models.branch import Branch, BranchSettings, PaymentGatewayConfig, CommunicationConfig, PlatformConfig
from models.academic import AcademicYear, Class, Section, Subject, ClassSubject
from models.student import Student, StudentDocument
from models.teacher import Teacher
from models.attendance import Attendance
from models.exam import Exam, ExamSubject, Marks
from models.fee import FeeStructure, FeeRecord
from models.notification import Notification, Announcement
from models.syllabus import Syllabus, QuestionPaper, ModelTestPaper
from models.activity import Activity, StudentActivity
from models.id_card import IDCardTemplate
from models.prelaunch import AuditLog, AuditAction
from models.messaging import MessageThread, ThreadParticipant, Message, Complaint, ComplaintStatus, ThreadType
from models.subscription import Plan, SchoolSubscription, PaymentHistory, PlanTier, SubscriptionStatus
from models.timetable import (
    PeriodDefinition, TimetableSlot, BellScheduleTemplate,
    ClassScheduleAssignment, SubjectHoursConfig, Substitution,
    SubstitutionStatus
)
from models.period_log import PeriodLog
from models.teacher_attendance import TeacherAttendance, LeaveRequest
from models.login_security import LoginAttempt, BannedIP
from models.payment import PaymentTransaction, Donation, NotificationLog
from models.registration_config import RegistrationNumberConfig

# Split from mega_modules.py into domain files
from models.transport import Vehicle, TransportRoute, RouteStop, StudentTransport
from models.employee import EmployeeType, Employee, SalarySlip
from models.admission import AdmissionStatus, Admission
from models.homework import Homework, HomeworkSubmission
from models.library import Book, BookIssue
from models.certificate import CertificateType, Certificate
from models.remark import RemarkCategory, RemarkTag, StudentRemark
from models.event import EventType, SchoolEvent
from models.student_leave import LeaveReasonType, ApprovalStatus, StudentLeave
from models.health import StudentHealth
from models.achievement import AchievementCategory, StudentAchievement
from models.diary import DiaryEntryType, DailyDiary
from models.board_result import BoardResult
from models.teacher_award import TeacherAward
from models.promotion import StudentPromotion
from models.quiz import Quiz, QuizQuestion, QuizAttempt
from models.accounts import AccountTransaction, SmsLog
from models.fee_waiver import FeeWaiver
from models.attendance_fine import AttendanceFineRule, AttendanceFine
from models.hostel import Hostel, HostelRoom, HostelAllocation
from models.house import House, StudentHouse
from models.student_role import StudentRole
from models.digital_library import DigitalContent, ContentView
from models.asset import AssetCategory, Asset, AssetLog
from models.photo_request import PhotoChangeRequest, PhotoApprovalStatus
from models.online_class import (
    OnlinePlatformConfig, TeacherPlatformToken, OnlineClass, LectureAttendance,
    OnlinePlatform, OnlineClassStatus, LectureAttendanceType
)

# Report Card Management System
from models.report_card import (
    ReportCardTemplate, ExamGroup, ExamCycle, MarksUploadTracker,
    StudentMarks, StudentResult, MarksAuditLog, ReportCardPDF,
    ExamCycleStatus, UploadStatus, SpecialCode, ResultStatus,
    AuditAction as RCAuditAction
)
