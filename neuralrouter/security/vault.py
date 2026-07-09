"""Credential vault — paper §6.4.

Secrets (API keys, tokens, passwords) live in the OS keychain when available,
otherwise in a Fernet-encrypted local store. They are referenced by *handle*;
the plaintext is resolved only at the moment of an authenticated call and is
never placed in the model context, logs, or a training corpus.

Backends, in order of preference:
  1. OS keychain via `keyring` (Keychain / Credential Manager / Secret Service)
  2. Fernet-encrypted file at $SARVA_VAULT_PATH (key from OMNI_VAULT_ENCRYPTION_KEY)
  3. In-process memory only (process lifetime) — last resort, warns

`redact(text)` strips any stored secret value from a string before it can reach
the model — the enforcement that does not depend on anyone remembering to.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SERVICE = "sarva-vault"
_VAULT_PATH = Path(os.environ.get("SARVA_VAULT_PATH", str(Path.home() / ".sarva" / "vault.enc")))
_ENC_KEY = os.environ.get("OMNI_VAULT_ENCRYPTION_KEY", "")

_lock = threading.Lock()
_mem: dict[str, str] = {}  # in-process fallback


def _keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:
        return None


def _fernet():
    if not _ENC_KEY:
        return None
    try:
        from cryptography.fernet import Fernet

        # Accept a raw urlsafe key, or derive a stable one from the passphrase.
        key = _ENC_KEY.encode()
        if len(key) != 44:  # not a Fernet key — derive
            import base64
            import hashlib

            key = base64.urlsafe_b64encode(hashlib.sha256(key).digest())
        return Fernet(key)
    except Exception as exc:
        logger.warning("Vault Fernet unavailable: %s", exc)
        return None


def _load_file() -> dict[str, str]:
    f = _fernet()
    if not f or not _VAULT_PATH.exists():
        return {}
    try:
        return json.loads(f.decrypt(_VAULT_PATH.read_bytes()).decode())
    except Exception:
        logger.exception("Vault file decrypt failed")
        return {}


def _save_file(data: dict[str, str]) -> bool:
    f = _fernet()
    if not f:
        return False
    try:
        _VAULT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _VAULT_PATH.write_bytes(f.encrypt(json.dumps(data).encode()))
        try:
            os.chmod(_VAULT_PATH, 0o600)
        except OSError:
            pass
        return True
    except Exception:
        logger.exception("Vault file write failed")
        return False


def store(handle: str, secret: str) -> dict:
    """Store a secret under a handle. Returns backend used (no secret echoed)."""
    if not handle or not secret:
        return {"ok": False, "error": "handle and secret required"}
    with _lock:
        kr = _keyring()
        if kr:
            try:
                kr.set_password(_SERVICE, handle, secret)
                return {"ok": True, "backend": "keyring", "handle": handle}
            except Exception:
                logger.warning("keyring store failed; falling back")
        data = _load_file()
        data[handle] = secret
        if _save_file(data):
            return {"ok": True, "backend": "encrypted_file", "handle": handle}
        _mem[handle] = secret
        logger.warning("Vault using in-memory fallback for %s (not persisted)", handle)
        return {"ok": True, "backend": "memory", "handle": handle}


def resolve(handle: str) -> Optional[str]:
    """Return the plaintext secret for a handle (call at the moment of use only)."""
    kr = _keyring()
    if kr:
        try:
            v = kr.get_password(_SERVICE, handle)
            if v is not None:
                return v
        except Exception:
            pass
    v = _load_file().get(handle)
    if v is not None:
        return v
    return _mem.get(handle)


def list_handles() -> list[str]:
    """Handles only — never values."""
    handles = set(_mem) | set(_load_file())
    return sorted(handles)


def delete(handle: str) -> dict:
    with _lock:
        kr = _keyring()
        if kr:
            try:
                kr.delete_password(_SERVICE, handle)
            except Exception:
                pass
        data = _load_file()
        data.pop(handle, None)
        _save_file(data)
        _mem.pop(handle, None)
    return {"ok": True, "handle": handle}


def redact(text: str) -> str:
    """Remove any stored secret value from a string before it reaches the model."""
    if not text:
        return text
    secrets = list(_mem.values()) + list(_load_file().values())
    kr = _keyring()
    if kr:
        for h in list_handles():
            try:
                v = kr.get_password(_SERVICE, h)
                if v:
                    secrets.append(v)
            except Exception:
                pass
    for s in secrets:
        if s and len(s) >= 6 and s in text:
            text = text.replace(s, "‹redacted›")
    return text
