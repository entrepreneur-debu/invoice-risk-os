import pytest

from app.core.errors import InvalidInput
from app.core.security import (
    FieldEncryptor,
    csrf_token_for,
    generate_token,
    hash_password,
    hash_token,
    tokens_match,
    validate_password_policy,
    verify_password,
)
from app.models.enums import Role
from app.modules.permissions import ASSIGNABLE_ROLES, ROLE_PERMISSIONS, Permission, has_permission


def test_passwords_are_hashed_with_argon2_and_verified() -> None:
    hashed = hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert "correct horse" not in hashed
    assert verify_password("correct horse battery", hashed)
    assert not verify_password("wrong password!!", hashed)
    assert not verify_password("anything", None)
    assert not verify_password("anything", "not-a-hash")


@pytest.mark.parametrize("password", ["short", "aaaaaaaaaaaaaaaa", "a" * 129, "user@example.com"])
def test_password_policy_rejects_weak_passwords(password: str) -> None:
    with pytest.raises(InvalidInput):
        validate_password_policy(password, "user@example.com")


def test_tokens_are_random_and_stored_only_as_hmac() -> None:
    token = generate_token()
    assert len(token) >= 43 and token != generate_token()
    digest = hash_token(token, "secret-a")
    assert token not in digest and digest != hash_token(token, "secret-b")
    csrf = csrf_token_for(digest, "secret-a")
    assert tokens_match(csrf, csrf_token_for(digest, "secret-a"))
    assert not tokens_match(csrf, csrf_token_for(digest, "secret-b"))


def test_field_encryption_round_trip_binds_context_and_fingerprints() -> None:
    encryptor = FieldEncryptor(b"k" * 32)
    ciphertext = encryptor.encrypt("501002345678", associated_data="account-1")
    assert "501002345678" not in ciphertext and ciphertext.startswith("v1:")
    assert encryptor.decrypt(ciphertext, associated_data="account-1") == "501002345678"
    with pytest.raises(Exception):  # noqa: B017 - InvalidTag: ciphertext moved to another row
        encryptor.decrypt(ciphertext, associated_data="account-2")
    assert encryptor.encrypt("x", "a") != encryptor.encrypt("x", "a")  # random nonce
    assert encryptor.fingerprint("501002345678") == encryptor.fingerprint("501002345678")
    assert FieldEncryptor(b"j" * 32).fingerprint("501002345678") != encryptor.fingerprint(
        "501002345678"
    )


def test_permission_matrix() -> None:
    assert not has_permission(Role.VIEWER, Permission.INVOICE_REVIEW)
    assert not has_permission(Role.VIEWER, Permission.INVOICE_UPLOAD)
    assert has_permission(Role.REVIEWER, Permission.INVOICE_REVIEW)
    assert not has_permission(Role.REVIEWER, Permission.INVOICE_APPROVE_FINAL)
    assert not has_permission(Role.REVIEWER, Permission.VENDOR_BANK_VERIFY)
    assert not has_permission(Role.REVIEWER, Permission.RISK_OVERRIDE)
    assert has_permission(Role.ADMIN, Permission.INVOICE_APPROVE_FINAL)
    assert has_permission(Role.ADMIN, Permission.ORG_MANAGE_SETTINGS)
    assert (
        ROLE_PERMISSIONS[Role.VIEWER]
        < ROLE_PERMISSIONS[Role.REVIEWER]
        < ROLE_PERMISSIONS[Role.ADMIN]
    )
    assert Role.OWNER not in ASSIGNABLE_ROLES[Role.ADMIN]
    assert Role.ADMIN not in ASSIGNABLE_ROLES[Role.ADMIN]
    assert ASSIGNABLE_ROLES[Role.REVIEWER] == frozenset()
