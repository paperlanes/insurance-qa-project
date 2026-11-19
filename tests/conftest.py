import pytest
from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app


@pytest.fixture(scope="session")
def client():
    """A test client that calls the API directly, no server needed."""
    return TestClient(app)


@pytest.fixture(scope="session")
def health_policy():
    """Find a real active HEALTH policy to use in tests."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT policy_number, sum_assured, start_date
                FROM policies
                WHERE status = 'ACTIVE' AND policy_type = 'HEALTH'
                  AND start_date <= CURRENT_DATE
                ORDER BY policy_id
                LIMIT 1
                """
            )
            return cur.fetchone()
    finally:
        conn.close()


@pytest.fixture
def cleanup():
    """Collects claim numbers created during a test, then deletes them afterwards."""
    created = []
    yield created
    if created:
        conn = get_connection()
        try:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM claims WHERE claim_number = ANY(%s)", (created,))
            conn.commit()
        finally:
            conn.close()