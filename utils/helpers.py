import uuid
import re
from datetime import datetime


def generate_slug(name: str) -> str:
    """Generate URL-friendly slug from name"""
    slug = name.lower().strip()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return f"{slug}-{uuid.uuid4().hex[:6]}"


def generate_receipt_number(branch_code: str = "EF") -> str:
    """Generate unique receipt number"""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unique = uuid.uuid4().hex[:4].upper()
    return f"{branch_code}-{timestamp}-{unique}"


def generate_admission_number(branch_code: str, year: str, sequence: int) -> str:
    """Generate admission number like DPS-2025-0001"""
    return f"{branch_code}-{year}-{sequence:04d}"


def format_indian_currency(amount: float) -> str:
    """Format amount in Indian currency style"""
    if amount >= 10000000:
        return f"₹{amount/10000000:.2f} Cr"
    elif amount >= 100000:
        return f"₹{amount/100000:.2f} L"
    elif amount >= 1000:
        return f"₹{amount/1000:.1f}K"
    return f"₹{amount:,.0f}"


def format_date_indian(dt) -> str:
    """Format date in Indian style DD/MM/YYYY"""
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt)
    return dt.strftime("%d/%m/%Y") if dt else ""
