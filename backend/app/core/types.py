"""SQLAlchemy type that encrypts secrets with Fernet at rest."""

from __future__ import annotations

from sqlalchemy import Text, TypeDecorator

from app.core.crypto import decrypt_secret, encrypt_secret


class EncryptedText(TypeDecorator):
    """Transparent encrypt-on-write / decrypt-on-read Text column."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001, ARG002
        if value is None or value == "":
            return value
        return encrypt_secret(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001, ARG002
        if value is None or value == "":
            return value
        return decrypt_secret(value)
