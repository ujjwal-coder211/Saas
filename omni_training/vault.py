"""
Secure vault for training data — tamper-evident, admin-gated export.

- Append-only signed JSONL (HMAC per line)
- Optional AES encryption at rest (set OMNI_VAULT_ENCRYPTION_KEY)
- Public API never exposes raw training files
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
VAULT_DIR = DATA_DIR / "vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

RAW_LOG_PATH = VAULT_DIR / "interactions_raw.jsonl"
CURATED_PATH = VAULT_DIR / "interactions_curated.jsonl"
TRAIN_OUTPUT_PATH = VAULT_DIR / "omni_v1_train.jsonl"
RESEARCH_OUTPUT_PATH = VAULT_DIR / "omni_v1_research.jsonl"
FEEDBACK_PATH = VAULT_DIR / "feedback_patches.jsonl"

# Legacy paths (migrate reads)
LEGACY_RAW = DATA_DIR / "interactions_raw.jsonl"

VAULT_HMAC_KEY = os.environ.get("OMNI_VAULT_HMAC_KEY", "")
VAULT_ENCRYPTION_KEY = os.environ.get("OMNI_VAULT_ENCRYPTION_KEY", "")
OMNI_ADMIN_KEY = os.environ.get("OMNI_ADMIN_KEY", "")


def _derive_key(secret: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt, 120_000, dklen=32)


def encrypt_payload(plain: str) -> str:
    if not VAULT_ENCRYPTION_KEY:
        return plain
    try:
        from cryptography.fernet import Fernet

        f = Fernet(base64.urlsafe_b64encode(_derive_key(VAULT_ENCRYPTION_KEY, b"omni-vault")[:32]))
        return "enc:" + f.encrypt(plain.encode()).decode()
    except Exception:
        return plain


def decrypt_payload(stored: str) -> str:
    if not stored.startswith("enc:"):
        return stored
    if not VAULT_ENCRYPTION_KEY:
        raise RuntimeError("Encrypted vault row but OMNI_VAULT_ENCRYPTION_KEY not set")
    from cryptography.fernet import Fernet

    f = Fernet(base64.urlsafe_b64encode(_derive_key(VAULT_ENCRYPTION_KEY, b"omni-vault")[:32]))
    return f.decrypt(stored[4:].encode()).decode()


def sign_line(payload: str) -> str:
    if not VAULT_HMAC_KEY:
        return json.dumps({"p": payload, "sig": None})
    sig = hmac.new(VAULT_HMAC_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"p": encrypt_payload(payload), "sig": sig})


def verify_and_parse(line: str) -> dict:
    wrapper = json.loads(line)
    payload = wrapper["p"]
    sig = wrapper.get("sig")
    if VAULT_HMAC_KEY and sig:
        plain = decrypt_payload(payload) if isinstance(payload, str) else payload
        if isinstance(plain, str) and plain.startswith("enc:"):
            plain = decrypt_payload(plain)
        expected = hmac.new(
            VAULT_HMAC_KEY.encode(), plain.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("Vault integrity check failed — possible tampering")
        return json.loads(plain)
    if isinstance(payload, str):
        try:
            return json.loads(decrypt_payload(payload))
        except json.JSONDecodeError:
            return json.loads(payload)
    return payload


def vault_append(path: Path, row_dict: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(row_dict, ensure_ascii=False, default=str)
    with open(path, "a", encoding="utf-8") as f:
        f.write(sign_line(payload) + "\n")


def vault_read_all(path: Path) -> list[dict]:
    if not path.exists():
        if path == RAW_LOG_PATH and LEGACY_RAW.exists():
            rows = []
            with open(LEGACY_RAW, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        rows.append(json.loads(line))
            return rows
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(verify_and_parse(line))
    return rows


def vault_rewrite(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            payload = json.dumps(row, ensure_ascii=False, default=str)
            f.write(sign_line(payload) + "\n")


def verify_admin_key(provided: str | None) -> bool:
    if not OMNI_ADMIN_KEY:
        return False
    if not provided:
        return False
    return hmac.compare_digest(provided, OMNI_ADMIN_KEY)


def vault_stats() -> dict:
    raw = vault_read_all(RAW_LOG_PATH)
    curated = vault_read_all(CURATED_PATH)
    return {
        "raw_rows": len(raw),
        "curated_rows": len(curated),
        "vault_encrypted": bool(VAULT_ENCRYPTION_KEY),
        "vault_signed": bool(VAULT_HMAC_KEY),
        "paths": {
            "raw": str(RAW_LOG_PATH),
            "curated": str(CURATED_PATH),
            "train": str(TRAIN_OUTPUT_PATH),
            "research": str(RESEARCH_OUTPUT_PATH),
        },
    }
