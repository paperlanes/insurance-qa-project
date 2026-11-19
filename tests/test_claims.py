import pytest


def valid_claim(policy, **changes):
    """A valid claim body for the given policy. Pass changes to break one field."""
    body = {
        "policy_number": policy["policy_number"],
        "claim_type": "HOSPITALIZATION",
        "incident_date": str(policy["start_date"]),
        "claimed_amount": 50000,
    }
    body.update(changes)
    return body


# ---------- Basic endpoints ----------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_existing_claim(client):
    response = client.get("/claims/CLM000001")
    assert response.status_code == 200
    assert response.json()["claim_number"] == "CLM000001"


def test_get_missing_claim_returns_404(client):
    response = client.get("/claims/CLM999999")
    assert response.status_code == 404


def test_submit_valid_claim(client, health_policy, cleanup):
    response = client.post("/claims", json=valid_claim(health_policy))
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "SUBMITTED"
    cleanup.append(data["claim_number"])


# ---------- Business rules ----------

@pytest.mark.parametrize(
    "changes, expected_error",
    [
        ({"claimed_amount": 99_999_999}, "Claimed amount exceeds sum assured"),
        ({"claim_type": "DEATH"}, "DEATH claims are not allowed on HEALTH policies"),
        ({"incident_date": "2030-01-01"}, "Incident date cannot be in the future"),
        ({"incident_date": "2000-01-01"}, "Incident date is outside the policy period"),
    ],
)
def test_business_rules_reject_invalid_claims(client, health_policy, changes, expected_error):
    response = client.post("/claims", json=valid_claim(health_policy, **changes))
    assert response.status_code == 400
    assert expected_error in response.json()["detail"]


def test_all_errors_reported_together(client, health_policy):
    body = valid_claim(health_policy, claim_type="DEATH",
                       claimed_amount=99_999_999, incident_date="2030-01-01")
    response = client.post("/claims", json=body)
    assert response.status_code == 400
    assert len(response.json()["detail"]) >= 3


def test_negative_amount_rejected_by_pydantic(client, health_policy):
    response = client.post("/claims", json=valid_claim(health_policy, claimed_amount=-500))
    assert response.status_code == 422


def test_unknown_policy_returns_404(client, health_policy):
    response = client.post("/claims",
                           json=valid_claim(health_policy, policy_number="POL999999"))
    assert response.status_code == 404


# ---------- Status workflow ----------

def test_full_claim_workflow(client, health_policy, cleanup):
    # Create a claim
    claim = client.post("/claims", json=valid_claim(health_policy)).json()
    number = claim["claim_number"]
    cleanup.append(number)
    url = f"/claims/{number}/status"

    # Can't approve before review
    r = client.patch(url, json={"new_status": "APPROVED", "approved_amount": 45000})
    assert r.status_code == 400

    # Review -> approve (partial) -> pay
    assert client.patch(url, json={"new_status": "UNDER_REVIEW"}).status_code == 200

    r = client.patch(url, json={"new_status": "APPROVED", "approved_amount": 60000})
    assert r.status_code == 400  # more than claimed

    r = client.patch(url, json={"new_status": "APPROVED", "approved_amount": 45000})
    assert r.status_code == 200

    r = client.patch(url, json={"new_status": "PAID"})
    assert r.status_code == 200
    assert r.json()["settled_date"] is not None

    # PAID is final
    r = client.patch(url, json={"new_status": "REJECTED", "rejection_reason": "test"})
    assert r.status_code == 400


def test_reject_requires_reason(client, health_policy, cleanup):
    claim = client.post("/claims", json=valid_claim(health_policy)).json()
    cleanup.append(claim["claim_number"])
    r = client.patch(f"/claims/{claim['claim_number']}/status",
                     json={"new_status": "REJECTED"})
    assert r.status_code == 400