from app.auth.tokens import generate_token, hash_token


def test_generate_token_is_unique() -> None:
    assert generate_token() != generate_token()


def test_hash_token_is_deterministic_for_same_secret() -> None:
    token = generate_token()
    assert hash_token(token, "secret-a") == hash_token(token, "secret-a")


def test_hash_token_differs_across_secrets() -> None:
    """The whole point of keying by secret: rotating SESSION_SECRET must
    invalidate every stored session hash at once.
    """
    token = generate_token()
    assert hash_token(token, "secret-a") != hash_token(token, "secret-b")
