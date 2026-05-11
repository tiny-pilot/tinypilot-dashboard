"""String <-> ciphertext helpers for device secrets.

All secrets (Web UI credentials, automation tokens, CSRF tokens, license keys)
are stored as encrypted bytes via ``app.crypto``. Callers should never log
the decrypted return value.
"""

from pathlib import Path

from app.crypto import decrypt_bytes
from app.crypto import encrypt_bytes


def encrypt_secret(key_path: Path, value: str) -> bytes:
    """Encrypt a UTF-8 string with the install's Fernet key."""
    return encrypt_bytes(key_path, value.encode('utf-8'))


def decrypt_secret(key_path: Path, value: bytes) -> str:
    """Decrypt a ciphertext blob and decode it as UTF-8."""
    return decrypt_bytes(key_path, value).decode('utf-8')
