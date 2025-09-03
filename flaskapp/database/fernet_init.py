from cryptography.fernet import Fernet
import os
from sqlalchemy.types import TypeDecorator, LargeBinary

fernet = None

def init_fernet(app):
    global fernet
    key = app.config.get("FERNET_KEY") or os.environ["FERNET_KEY"]
    fernet = Fernet(key.encode() if isinstance(key, str) else key)



class EncryptedType(TypeDecorator):
    """Encrypts/decrypts values transparently using Fernet."""
    impl = LargeBinary

    def process_bind_param(self, value, dialect):
        """Called before storing to DB"""
        if value is None:
            return None
        if not isinstance(value, bytes):
            value = value.encode()
        return fernet.encrypt(value)

    def process_result_value(self, value, dialect):
        """Called when loading from DB"""
        if value is None:
            return None
        return fernet.decrypt(value).decode()

