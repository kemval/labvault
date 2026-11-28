"""
repo/passwords.py — salted, slow password hashing with stdlib scrypt (audit H6, ADR 0013).

Stored format:  scrypt$<n>$<r>$<p>$<salt hex>$<hash hex>
The cost is stored with each hash, so it can be raised later: verify() reads
it back, and needs_rehash() tells sign-in to upgrade older hashes.
"scrypt-sha256$..." is a migration-6 hash: scrypt over the legacy unsalted
SHA-256 digest, upgraded to plain scrypt at the user's next sign-in.
"""

import hashlib
import hmac
import os

# OWASP-recommended scrypt setting: about 16 MiB per hash.
COST = {"n": 2 ** 14, "r": 8, "p": 5}
SCHEME = "scrypt"
LEGACY_SCHEME = "scrypt-sha256"


def _scrypt(secret: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(secret.encode(), salt=salt, n=n, r=r, p=p,
                          maxmem=2 * 128 * n * r * p + 1024 * 1024, dklen=32)


def _encode(scheme: str, secret: str) -> str:
    salt = os.urandom(16)
    digest = _scrypt(secret, salt, **COST)
    return f"{scheme}${COST['n']}${COST['r']}${COST['p']}${salt.hex()}${digest.hex()}"


def hash_password(password: str) -> str:
    return _encode(SCHEME, password)


def wrap_legacy(sha256_hex: str) -> str:
    """Strengthen a stored unsalted SHA-256 digest without knowing the password."""
    return _encode(LEGACY_SCHEME, sha256_hex)


def verify(password: str, stored: str) -> bool:
    """True if `password` matches `stored`. Anything unparseable (e.g. the
    system accounts' "!") never matches."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        n, r, p, salt, digest = int(n), int(r), int(p), bytes.fromhex(salt), bytes.fromhex(digest)
    except (AttributeError, ValueError):
        return False
    if scheme == SCHEME:
        secret = password
    elif scheme == LEGACY_SCHEME:
        secret = hashlib.sha256(password.encode()).hexdigest()
    else:
        return False
    return hmac.compare_digest(_scrypt(secret, salt, n, r, p), digest)


def needs_rehash(stored: str) -> bool:
    parts = stored.split("$")
    return parts[0] != SCHEME or parts[1:4] != [str(COST[k]) for k in ("n", "r", "p")]


_DUMMY = None


def burn_time(password: str) -> None:
    """Spend one verification's worth of time, so an unknown username takes
    as long to refuse as a wrong password."""
    global _DUMMY
    if _DUMMY is None:
        _DUMMY = hash_password("not a real password")
    verify(password, _DUMMY)
