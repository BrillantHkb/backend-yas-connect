"""CRY-12/13 : wrap/unwrap AES-256-GCM des clés at-rest via CRYPTO_MASTER_KEY."""

import base64
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings

from apps.iam.exceptions import AuthAPIError

MSG_MASTER_UNSET = "CRYPTO_MASTER_KEY absente ou invalide (32 octets attendus)."

_NONCE_BYTES = 12


def _master_key() -> bytes:
    raw = (settings.CRYPTO_MASTER_KEY or "").strip()
    if not raw:
        raise AuthAPIError(500, "CRYPTO_MASTER_UNSET", MSG_MASTER_UNSET)
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise AuthAPIError(500, "CRYPTO_MASTER_UNSET", MSG_MASTER_UNSET) from exc
    if len(key) != 32:
        raise AuthAPIError(500, "CRYPTO_MASTER_UNSET", MSG_MASTER_UNSET)
    return key


def wrap(plaintext: bytes) -> bytes:
    """Retourne nonce(12o) || ciphertext+tag."""
    key = _master_key()
    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ciphertext


def unwrap(blob: bytes) -> bytes:
    key = _master_key()
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except InvalidTag as exc:
        raise AuthAPIError(500, "CRYPTO_MASTER_UNSET", MSG_MASTER_UNSET) from exc
