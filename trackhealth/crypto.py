"""Garmin Token encryption for one TrackHealth OS Instance."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet


class MissingEncryptionKey(RuntimeError):
    """Raised when Token encryption is requested without TH_ENC_KEY."""


def load_key_from_env() -> bytes:
    value = os.environ.get("TH_ENC_KEY", "").strip()
    if not value:
        raise MissingEncryptionKey("TH_ENC_KEY must be set to encrypt or decrypt the Token")
    return value.encode("ascii")


def encrypt_token(plaintext: str) -> bytes:
    return Fernet(load_key_from_env()).encrypt(plaintext.encode("utf-8"))


def decrypt_token(blob: bytes) -> str:
    return Fernet(load_key_from_env()).decrypt(blob).decode("utf-8")


def generate_key() -> str:
    return Fernet.generate_key().decode("ascii")
