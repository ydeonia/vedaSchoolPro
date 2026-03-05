import uuid, random, string, re
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

def _to_base36(num, min_length=3):
    if num == 0: return '0' * min_length
    chars = string.digits + string.ascii_uppercase
    result = ''
    while num > 0:
        result = chars[num % 36] + result
        num //= 36
    return result.zfill(min_length)

def _random_alphanum(length):
    return ''.join(random.choices(string.digits + string.ascii_uppercase, k=length))

def _class_code(class_name):
    name = (class_name or "").strip().upper()
    if "NUR" in name: return "NUR"
    if "LKG" in name: return "LKG"
    if "UKG" in name: return "UKG"
    nums = re.findall(r'\d+', name)
    return nums[0].zfill(2) if nums else "00"

async def generate_student_registration_id(db, branch_id, admission_year, class_name="", gender="", school_name=""):
    from models.branch import Branch
    branch_uuid = uuid.UUID(branch_id) if isinstance(branch_id, str) else branch_id

    config = None
    try:
        from models.registration_config import RegistrationNumberConfig
        config = (await db.execute(
            select(RegistrationNumberConfig).where(RegistrationNumberConfig.branch_id == branch_uuid)
        )).scalar_one_or_none()
    except Exception:
        pass

    if not school_name:
        branch = await db.scalar(select(Branch).where(Branch.id == branch_uuid))
        school_name = branch.name if branch else "SCHOOL"

    if config:
        fmt = config.format_template
        school_code = config.school_code or school_name[:4].upper().replace(" ", "")
        use_base36 = config.use_base36
        if config.current_year != admission_year:
            config.current_year = admission_year
            config.current_sequence = 0
        config.current_sequence = (config.current_sequence or 0) + 1
        seq = config.current_sequence
    else:
        fmt = "{SCHOOL4}{YY}{SEQ4}"
        school_code = school_name[:4].upper().replace(" ", "")
        use_base36 = False
        from models.student import Student
        seq = (await db.scalar(select(func.count(Student.id)).where(
            Student.branch_id == branch_uuid, Student.student_login_id.isnot(None))) or 0) + 1

    gender_code = "M" if gender and gender.lower().startswith("m") else \
                  "F" if gender and gender.lower().startswith("f") else "O"

    tokens = {
        "{SCHOOL4}": school_name[:4].upper().replace(" ", ""),
        "{SCHOOL3}": school_name[:3].upper().replace(" ", ""),
        "{CODE}": school_code,
        "{YY}": str(admission_year % 100).zfill(2),
        "{YYYY}": str(admission_year),
        "{CLASS}": _class_code(class_name),
        "{GENDER}": gender_code,
        "{SEQ3}": _to_base36(seq, 3) if use_base36 else str(seq),
        "{SEQ4}": _to_base36(seq, 4) if use_base36 else str(seq),
        "{SEQ5}": _to_base36(seq, 5) if use_base36 else str(seq),
        "{RAND4}": _random_alphanum(4),
        "{RAND6}": _random_alphanum(6),
    }

    result_id = fmt
    for token, value in tokens.items():
        result_id = result_id.replace(token, value)

    # Uniqueness check
    from models.student import Student
    if await db.scalar(select(Student.id).where(Student.student_login_id == result_id)):
        result_id += _random_alphanum(2)

    return result_id