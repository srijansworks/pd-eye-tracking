"""Send a measurement batch to the backend API.

Auth: a per-device ingest key (created by a study member in the database,
shown once, stored only as a SHA-256 hash). It is NOT a Supabase service-role
key — a leaked device key can only append data to its own study.

Environment variables (see .env.example):
  EYETRACK_API_URL     e.g. http://localhost:3000
  EYETRACK_DEVICE_KEY  e.g. dk_...
"""

from __future__ import annotations

import os

import requests


def _cfg(api_url: str | None, key: str | None) -> tuple[str, str]:
    api_url = (api_url or os.environ.get("EYETRACK_API_URL", "")).rstrip("/")
    key = key or os.environ.get("EYETRACK_DEVICE_KEY", "")
    if not api_url or not key:
        raise SystemExit("Set EYETRACK_API_URL and EYETRACK_DEVICE_KEY (see .env.example).")
    return api_url, key


def create_session(participant_code: str, protocol: str = "eye_v1",
                   api_url: str | None = None, key: str | None = None) -> str:
    api_url, key = _cfg(api_url, key)
    r = requests.post(f"{api_url}/api/v1/sessions", timeout=15,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"participant_code": participant_code, "protocol": protocol})
    if r.status_code >= 300:
        raise SystemExit(f"Session creation failed ({r.status_code}): {r.text}")
    return r.json()["session_id"]


def upload_batch(batch: dict, api_url: str | None = None, key: str | None = None) -> dict:
    api_url, key = _cfg(api_url, key)
    if not batch.get("session_id"):
        raise SystemExit("Batch has no session_id; pass --session-id or --participant.")
    r = requests.post(f"{api_url}/api/v1/ingest", timeout=30,
                      headers={"Authorization": f"Bearer {key}"}, json=batch)
    if r.status_code >= 300:
        raise SystemExit(f"Upload failed ({r.status_code}): {r.text}")
    return r.json()
