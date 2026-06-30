import pytest
from cryptography.fernet import InvalidToken

from trackhealth.crypto import (
    MissingEncryptionKey,
    decrypt_token,
    encrypt_token,
    generate_key,
    load_key_from_env,
)


def test_encrypt_decrypt_token_round_trips(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_ENC_KEY", generate_key())

    ciphertext = encrypt_token("garmin-token")

    assert ciphertext != b"garmin-token"
    assert decrypt_token(ciphertext) == "garmin-token"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_encryption_key_raises(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("TH_ENC_KEY", raising=False)
    else:
        monkeypatch.setenv("TH_ENC_KEY", value)

    with pytest.raises(MissingEncryptionKey, match="TH_ENC_KEY"):
        load_key_from_env()


def test_wrong_encryption_key_fails_to_decrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TH_ENC_KEY", generate_key())
    ciphertext = encrypt_token("garmin-token")
    monkeypatch.setenv("TH_ENC_KEY", generate_key())

    with pytest.raises(InvalidToken):
        decrypt_token(ciphertext)
