"""Fernet-backed encryption for at-rest secrets.

The dashboard creates a single 32-byte Fernet key on first run (default
location: ``data/secret.key``) and reuses it for every encrypted column. Back
up this file together with the SQLite database; without it, the encrypted
columns cannot be recovered.
"""

from pathlib import Path

from cryptography.fernet import Fernet


def _load_or_create_key(key_path: Path) -> bytes:
    """Return the install's Fernet key, generating one if missing."""
    if not key_path.exists():
        key_path.parent.mkdir(parents=True, exist_ok=True)
        key_path.write_bytes(Fernet.generate_key())
    return key_path.read_bytes()


def encrypt_bytes(key_path: Path, data: bytes) -> bytes:
    """Encrypt arbitrary bytes with the install key."""
    return Fernet(_load_or_create_key(key_path)).encrypt(data)


def decrypt_bytes(key_path: Path, ciphertext: bytes) -> bytes:
    """Decrypt bytes previously produced by :func:`encrypt_bytes`."""
    return Fernet(_load_or_create_key(key_path)).decrypt(ciphertext)
