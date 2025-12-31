"""
Pytest smoke tests for the live API server.

Usage:
  pip install pytest requests
  export API_BASE_URL=http://localhost:8000/api/v1
  export API_ADMIN_EMAIL=admin@example.com
  export API_ADMIN_PASSWORD=changeme
  # Optional sample IDs for read/update tests
  export SAMPLE_COMPANY_ID=<uuid>
  export SAMPLE_JOB_ID=<uuid>
  export SAMPLE_CANDIDATE_ID=<uuid>
  export SAMPLE_INTERVIEW_ID=<uuid>
  pytest -q backend/tests/test_api_smoke.py
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta

import pytest
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1").rstrip("/")
ADMIN_EMAIL = os.getenv("API_ADMIN_EMAIL", "")
ADMIN_PASSWORD = os.getenv("API_ADMIN_PASSWORD", "")

SAMPLE_COMPANY_ID = os.getenv("SAMPLE_COMPANY_ID")
SAMPLE_JOB_ID = os.getenv("SAMPLE_JOB_ID")
SAMPLE_CANDIDATE_ID = os.getenv("SAMPLE_CANDIDATE_ID")
SAMPLE_INTERVIEW_ID = os.getenv("SAMPLE_INTERVIEW_ID")


@pytest.fixture(scope="session")
def session():
    sess = requests.Session()
    # health check does not require auth
    resp = sess.get(f"{BASE_URL}/health")
    resp.raise_for_status()
    return sess


@pytest.fixture(scope="session")
def token(session: requests.Session):
    if not ADMIN_EMAIL or not ADMIN_PASSWORD:
        pytest.skip("Set API_ADMIN_EMAIL and API_ADMIN_PASSWORD for auth tests")
    resp = session.post(
        f"{BASE_URL}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    resp.raise_for_status()
    data = resp.json()["data"]
    return data["access_token"]


@pytest.fixture(scope="session")
def authed(session: requests.Session, token: str):
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


def _uuid_or_none(val: str | None):
    if not val:
        return None
    return uuid.UUID(str(val))


def test_health(session: requests.Session):
    resp = session.get(f"{BASE_URL}/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_list_companies(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/companies", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


def test_list_jobs(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/jobs", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


def test_list_candidates(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/candidates", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


@pytest.mark.skipif(not SAMPLE_JOB_ID, reason="Set SAMPLE_JOB_ID to run this test")
def test_get_job(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/jobs/{SAMPLE_JOB_ID}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == SAMPLE_JOB_ID


@pytest.mark.skipif(not SAMPLE_CANDIDATE_ID, reason="Set SAMPLE_CANDIDATE_ID to run this test")
def test_get_candidate(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/candidates/{SAMPLE_CANDIDATE_ID}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == SAMPLE_CANDIDATE_ID


def test_list_interviews(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/interviews", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


@pytest.mark.skipif(not SAMPLE_INTERVIEW_ID, reason="Set SAMPLE_INTERVIEW_ID to run this test")
def test_get_interview(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/interviews/{SAMPLE_INTERVIEW_ID}")
    assert resp.status_code == 200
    assert resp.json()["data"]["id"] == SAMPLE_INTERVIEW_ID


@pytest.mark.skipif(not SAMPLE_INTERVIEW_ID, reason="Set SAMPLE_INTERVIEW_ID to run this test")
def test_patch_interview_status(authed: requests.Session):
    resp = authed.patch(
        f"{BASE_URL}/interviews/{SAMPLE_INTERVIEW_ID}/status",
        json={"status": "ON_HOLD"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == "ON_HOLD"


def test_payments_pending_dues(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/payments/pending-dues")
    assert resp.status_code == 200
    assert isinstance(resp.json()["data"], list)


def test_payments_ledger(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/payments/ledger", params={"page": 1, "limit": 5})
    assert resp.status_code == 200
    assert "items" in resp.json()["data"]


@pytest.mark.skipif(not SAMPLE_COMPANY_ID, reason="Set SAMPLE_COMPANY_ID to run this test")
def test_create_company_payment(authed: requests.Session):
    # Requires sample company id; amount/time randomized
    payload = {
        "company_id": SAMPLE_COMPANY_ID,
        "amount": 123,
        "payment_date": datetime.utcnow().isoformat() + "Z",
        "remarks": "smoke test payment",
    }
    resp = authed.post(f"{BASE_URL}/payments", json=payload)
    assert resp.status_code in (200, 201, 409)
    if resp.status_code == 200:
        assert resp.json()["data"]["amount"] == 123


@pytest.mark.skipif(not SAMPLE_CANDIDATE_ID, reason="Set SAMPLE_CANDIDATE_ID to run this test")
def test_candidate_payment_flow(authed: requests.Session):
    payload = {
        "amount": 111,
        "payment_date": datetime.utcnow().isoformat() + "Z",
        "remarks": "smoke candidate payment",
    }
    resp = authed.post(f"{BASE_URL}/candidate-payments/{SAMPLE_CANDIDATE_ID}/payments", json=payload)
    assert resp.status_code in (200, 400, 404)


@pytest.mark.skipif(not SAMPLE_CANDIDATE_ID, reason="Set SAMPLE_CANDIDATE_ID to run this test")
def test_candidate_get_payments(authed: requests.Session):
    resp = authed.get(f"{BASE_URL}/candidate-payments/candidates/{SAMPLE_CANDIDATE_ID}/payments")
    assert resp.status_code in (200, 404)
    if resp.status_code == 200:
        assert isinstance(resp.json()["data"], list)
