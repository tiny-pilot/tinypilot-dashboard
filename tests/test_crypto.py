from pathlib import Path

from app.crypto import decrypt_bytes
from app.crypto import encrypt_bytes


def test_encrypt_roundtrip(tmp_path):
    key_file = Path(tmp_path) / 'secret.key'
    payload = b'automation-license-key-abc'

    ciphertext = encrypt_bytes(key_file, payload)
    assert ciphertext != payload

    plaintext = decrypt_bytes(key_file, ciphertext)
    assert plaintext == payload
