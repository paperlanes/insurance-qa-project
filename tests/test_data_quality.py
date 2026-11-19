import pytest

from app.db import get_connection

# Every test in this file gets the data_quality label
pytestmark = pytest.mark.data_quality


def find_bad_rows(sql):
    """Run a validation query and return the rows it finds."""
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchall()
    finally:
        conn.close()


def claim_numbers(rows):
    """First 10 claim numbers from the results, for the error message."""
    return [row["claim_number"] for row in rows][:10]


# ---------- Checks we expect to FAIL (defects seeded in the data) ----------

def test_no_incidents_after_policy_end():
    bad = find_bad_rows("""
        SELECT c.claim_number
        FROM claims c
        JOIN policies p ON p.policy_id = c.policy_id
        WHERE c.incident_date > p.end_date
    """)
    assert not bad, f"{len(bad)} claims have an incident after the policy ended: {claim_numbers(bad)}"


def test_no_claims_above_sum_assured():
    bad = find_bad_rows("""
        SELECT c.claim_number
        FROM claims c
        JOIN policies p ON p.policy_id = c.policy_id
        WHERE c.claimed_amount > p.sum_assured
    """)
    assert not bad, f"{len(bad)} claims exceed the sum assured: {claim_numbers(bad)}"


def test_no_invalid_claims_paid_out():
    bad = find_bad_rows("""
        SELECT c.claim_number
        FROM claims c
        JOIN policies p ON p.policy_id = c.policy_id
        WHERE c.status IN ('APPROVED', 'PAID')
          AND (c.incident_date > p.end_date OR c.claimed_amount > p.sum_assured)
    """)
    assert not bad, f"{len(bad)} invalid claims were approved or paid: {claim_numbers(bad)}"


# ---------- Checks we expect to PASS (data is consistent here) ----------

def test_approved_amount_never_exceeds_claimed():
    bad = find_bad_rows("""
        SELECT claim_number FROM claims
        WHERE approved_amount > claimed_amount
    """)
    assert not bad, f"{len(bad)} claims approved for more than claimed: {claim_numbers(bad)}"


def test_paid_claims_have_settlement_date():
    bad = find_bad_rows("""
        SELECT claim_number FROM claims
        WHERE status = 'PAID' AND settled_date IS NULL
    """)
    assert not bad, f"{len(bad)} paid claims have no settlement date: {claim_numbers(bad)}"


def test_rejected_claims_have_reason():
    bad = find_bad_rows("""
        SELECT claim_number FROM claims
        WHERE status = 'REJECTED' AND rejection_reason IS NULL
    """)
    assert not bad, f"{len(bad)} rejected claims have no reason: {claim_numbers(bad)}"