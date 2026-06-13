"""Fernet credential encryption (PLAT-07, D-06, T-01-16).

MultiFernet keyed from settings.credential_keys: the FIRST key encrypts,
ALL keys decrypt — rotation-ready (add a new key at the front, re-encrypt
lazily, drop the old key later).

This module deliberately has NO logger and never logs its inputs.
"""

from cryptography.fernet import Fernet, MultiFernet

from app.core.config import settings

fernet = MultiFernet([Fernet(key) for key in settings.credential_keys])


def encrypt(value: str) -> bytes:
    """Encrypt a plaintext credential to a Fernet token (authenticated encryption)."""
    return fernet.encrypt(value.encode())


def decrypt(token: bytes) -> str:
    """Decrypt a Fernet token back to the original plaintext."""
    return fernet.decrypt(token).decode()
