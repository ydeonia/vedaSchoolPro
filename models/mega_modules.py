"""
Backward-compatibility shim — all models have been split into domain-specific files.
Import from individual modules (e.g., models.transport, models.employee) instead.
"""
# Transport
from models.transport import Vehicle, TransportRoute, RouteStop, StudentTransport
# HR / Employee
from models.employee import EmployeeType, Employee, SalarySlip
# Admissions
from models.admission import AdmissionStatus, Admission
# Homework
from models.homework import Homework, HomeworkSubmission
# Library
from models.library import Book, BookIssue
# Certificates
from models.certificate import CertificateType, Certificate
# Teacher Remarks
from models.remark import RemarkCategory, RemarkTag, StudentRemark
# Events
from models.event import EventType, SchoolEvent
# Student Leave
from models.student_leave import LeaveReasonType, ApprovalStatus, StudentLeave
# Health Records
from models.health import StudentHealth
# Achievements
from models.achievement import AchievementCategory, StudentAchievement
# Daily Diary
from models.diary import DiaryEntryType, DailyDiary
# Board Results
from models.board_result import BoardResult
# Teacher Awards
from models.teacher_award import TeacherAward
# Student Promotion
from models.promotion import StudentPromotion
# Quizzes
from models.quiz import Quiz, QuizQuestion, QuizAttempt
# Accounts
from models.accounts import AccountTransaction, SmsLog
# Fee Waivers
from models.fee_waiver import FeeWaiver
# Attendance Fines
from models.attendance_fine import AttendanceFineRule, AttendanceFine
# Hostel
from models.hostel import Hostel, HostelRoom, HostelAllocation
# House System
from models.house import House, StudentHouse
# Student Roles
from models.student_role import StudentRole
# Digital Library
from models.digital_library import DigitalContent, ContentView
