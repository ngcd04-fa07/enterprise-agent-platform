from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Argon2id (argon2-cffi's default variant) — current OWASP-recommended
# default for password hashing, ahead of bcrypt/scrypt/PBKDF2.
_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    return True
