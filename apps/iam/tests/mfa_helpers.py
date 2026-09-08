"""Helpers AUTH-C : facteur 1 → TOTP (secret Fernet de test) → JWT."""

import pyotp

from apps.iam.models import User
from apps.iam.services.mfa_service import decrypt_totp_secret


def totp_now(user: User) -> str:
    """Code Authenticator courant (secret déchiffré en base)."""
    user = User.objects.select_related("otp_secret").get(pk=user.pk)
    rec = user.otp_secret
    b32 = decrypt_totp_secret(rec.secret)
    return pyotp.TOTP(b32, digits=rec.digits, interval=rec.period).now()


def post_mfa_verify(api, *, mfa_token: str, user=None, otp=None, backup_code=None):
    """otp XOR backup. Si otp omis : code courant depuis otp_secrets."""
    body = {"mfa_token": mfa_token}
    if backup_code is not None:
        body["backup_code"] = backup_code
    else:
        body["otp"] = otp if otp is not None else totp_now(user)
    return api.post("/api/v1/auth/mfa/verify", body, format="json")


def login_until_jwt(
    api,
    *,
    password: str,
    device: dict,
    email=None,
    username=None,
    path="/api/v1/auth/login",
):
    """Facteur 1 + TOTP. Le 200 login n’a pas de JWT."""
    body = {"password": password, "device": device}
    if email:
        body["email"] = email
    if username:
        body["username"] = username
    r = api.post(path, body, format="json")
    assert r.status_code == 200, r.data
    data = r.data["data"]
    assert data.get("mfa_required") is True
    assert "access_token" not in data
    if email:
        user = User.objects.get(email=email)
    else:
        user = User.objects.get(username=username)
    v = post_mfa_verify(api, mfa_token=data["mfa_token"], user=user)
    assert v.status_code == 200, v.data
    return v
