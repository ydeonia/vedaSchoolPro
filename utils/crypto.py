"""
Encryption utilities for sensitive data stored in database.
Uses Fernet symmetric encryption (AES-128-CBC with HMAC-SHA256).
"""
import os
import base64
import hashlib
from cryptography.fernet import Fernet

# Derive a Fernet key from the app's SECRET_KEY
# This ensures consistent encryption/decryption across restarts
def _get_fernet_key() -> bytes:
    from config import settings
    key_bytes = settings.SECRET_KEY.encode('utf-8')
    # Use SHA-256 to get exactly 32 bytes, then base64-encode for Fernet
    digest = hashlib.sha256(key_bytes).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    return Fernet(_get_fernet_key())


def encrypt_value(plaintext: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a previously encrypted value. Returns plaintext string."""
    if not ciphertext:
        return ciphertext
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except Exception:
        # If decryption fails (e.g., value was stored before encryption was enabled),
        # return as-is so the system doesn't break on legacy data
        return ciphertext


def mask_aadhaar(aadhaar: str) -> str:
    """Mask Aadhaar number, showing only last 4 digits. e.g., XXXX-XXXX-1234"""
    if not aadhaar:
        return ""
    clean = aadhaar.replace(" ", "").replace("-", "")
    if len(clean) < 4:
        return "XXXX-XXXX-XXXX"
    return f"XXXX-XXXX-{clean[-4:]}"


def mask_account_number(account: str) -> str:
    """Mask bank account number, showing only last 4 digits."""
    if not account:
        return ""
    if len(account) <= 4:
        return account
    return "X" * (len(account) - 4) + account[-4:]
