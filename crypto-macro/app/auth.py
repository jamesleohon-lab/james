"""Single-user passcode login using a signed cookie."""

import hashlib
import hmac
import time

COOKIE_NAME = "cm_session"
SESSION_DAYS = 180


def _secret(secret_key: str, passcode: str) -> bytes:
    # Fall back to a key derived from the passcode, so changing the passcode
    # also logs out every existing session.
    return (secret_key or f"derived:{passcode}").encode()


def make_token(secret_key: str, passcode: str, now: float | None = None) -> str:
    expires = int((now or time.time()) + SESSION_DAYS * 86400)
    sig = hmac.new(_secret(secret_key, passcode), str(expires).encode(),
                   hashlib.sha256).hexdigest()
    return f"{expires}.{sig}"


def check_token(token: str | None, secret_key: str, passcode: str,
                now: float | None = None) -> bool:
    if not token or "." not in token:
        return False
    expires, sig = token.split(".", 1)
    if not expires.isdigit() or int(expires) < (now or time.time()):
        return False
    expected = hmac.new(_secret(secret_key, passcode), expires.encode(),
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)


def check_passcode(given: str, passcode: str) -> bool:
    return bool(passcode) and hmac.compare_digest(given.encode(), passcode.encode())
