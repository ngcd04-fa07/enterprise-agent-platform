from app.auth.password import hash_password, verify_password


def test_verify_password_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", hashed)


def test_hash_password_is_not_plaintext() -> None:
    assert hash_password("correct horse battery staple") != "correct horse battery staple"
