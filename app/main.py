from datetime import date
from decimal import Decimal
from typing import Literal,Optional

from fastapi import FastAPI, HTTPException,Query
from pydantic import BaseModel, Field

from app.db import get_connection

app = FastAPI(title="Insurance Claims API")


# ---------- Request model ----------
class ClaimCreate(BaseModel):
    policy_number: str
    claim_type: Literal["HOSPITALIZATION", "OUTPATIENT", "CRITICAL_ILLNESS", "DEATH"]
    incident_date: date
    claimed_amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


# Which claim types each policy type allows
ALLOWED_CLAIM_TYPES = {
    "HEALTH": {"HOSPITALIZATION", "OUTPATIENT"},
    "LIFE": {"DEATH"},
    "CRITICAL_ILLNESS": {"CRITICAL_ILLNESS"},
}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/claims/{claim_number}")
def get_claim(claim_number: str):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.claim_number, c.claim_type, c.status,
                       c.incident_date, c.submitted_date,
                       c.claimed_amount, c.approved_amount,
                       c.rejection_reason, c.settled_date,
                       p.policy_number, p.policy_type, p.sum_assured
                FROM claims c
                JOIN policies p ON p.policy_id = c.policy_id
                WHERE c.claim_number = %s
                """,
                (claim_number,),
            )
            claim = cur.fetchone()
    finally:
        conn.close()

    if claim is None:
        raise HTTPException(status_code=404, detail=f"Claim {claim_number} not found")
    return claim


@app.post("/claims", status_code=201)
def submit_claim(claim: ClaimCreate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # 1. The policy must exist
            cur.execute(
                """
                SELECT policy_id, policy_type, sum_assured, start_date, end_date, status
                FROM policies
                WHERE policy_number = %s
                """,
                (claim.policy_number,),
            )
            policy = cur.fetchone()
            if policy is None:
                raise HTTPException(status_code=404,
                                    detail=f"Policy {claim.policy_number} not found")

            # 2. Business rules: collect ALL problems, not just the first one
            errors = []
            if claim.incident_date > date.today():
                errors.append("Incident date cannot be in the future")
            if not (policy["start_date"] <= claim.incident_date <= policy["end_date"]):
                errors.append("Incident date is outside the policy period")
            if policy["status"] in ("LAPSED", "CANCELLED"):
                errors.append(f"Policy is {policy['status']}")
            if claim.claim_type not in ALLOWED_CLAIM_TYPES[policy["policy_type"]]:
                errors.append(f"{claim.claim_type} claims are not allowed "
                              f"on {policy['policy_type']} policies")
            if claim.claimed_amount > policy["sum_assured"]:
                errors.append("Claimed amount exceeds sum assured")

            if errors:
                raise HTTPException(status_code=400, detail=errors)

            # 3. Generate the next claim number from the database sequence
            cur.execute("SELECT nextval('claims_claim_id_seq') AS id")
            new_id = cur.fetchone()["id"]
            claim_number = f"CLM{new_id:06d}"

            # 4. Save the claim
            cur.execute(
                """
                INSERT INTO claims (claim_id, claim_number, policy_id, claim_type,
                                    incident_date, claimed_amount)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING claim_number, status, submitted_date
                """,
                (new_id, claim_number, policy["policy_id"], claim.claim_type,
                 claim.incident_date, claim.claimed_amount),
            )
            created = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    return created
# ---------- GET /claims: list with optional filters ----------
@app.get("/claims")
def list_claims(
    status: Optional[Literal["SUBMITTED", "UNDER_REVIEW", "APPROVED", "REJECTED", "PAID"]] = None,
    policy_type: Optional[Literal["HEALTH", "LIFE", "CRITICAL_ILLNESS"]] = None,
    limit: int = Query(20, ge=1, le=100),
):
    query = """
        SELECT c.claim_number, c.claim_type, c.status, c.claimed_amount,
               c.submitted_date, p.policy_number, p.policy_type
        FROM claims c
        JOIN policies p ON p.policy_id = c.policy_id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND c.status = %s"
        params.append(status)
    if policy_type:
        query += " AND p.policy_type = %s"
        params.append(policy_type)
    query += " ORDER BY c.submitted_date DESC LIMIT %s"
    params.append(limit)

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    finally:
        conn.close()


# ---------- PATCH /claims/{claim_number}/status: move a claim through its workflow ----------
class ClaimStatusUpdate(BaseModel):
    new_status: Literal["UNDER_REVIEW", "APPROVED", "REJECTED", "PAID"]
    approved_amount: Optional[Decimal] = Field(default=None, ge=0)
    rejection_reason: Optional[str] = None


# Which status a claim can move to from its current status
ALLOWED_TRANSITIONS = {
    "SUBMITTED":    {"UNDER_REVIEW", "REJECTED"},
    "UNDER_REVIEW": {"APPROVED", "REJECTED"},
    "APPROVED":     {"PAID"},
    "REJECTED":     set(),   # final, no changes allowed
    "PAID":         set(),   # final
}


@app.patch("/claims/{claim_number}/status")
def update_claim_status(claim_number: str, update: ClaimStatusUpdate):
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            # Lock this claim's row so two people can't update it at the same time
            cur.execute(
                "SELECT claim_id, status, claimed_amount FROM claims "
                "WHERE claim_number = %s FOR UPDATE",
                (claim_number,),
            )
            claim = cur.fetchone()
            if claim is None:
                raise HTTPException(status_code=404, detail=f"Claim {claim_number} not found")

            # Rule 1: only allowed status transitions
            if update.new_status not in ALLOWED_TRANSITIONS[claim["status"]]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot change status from {claim['status']} to {update.new_status}",
                )

            # Rule 2: approval needs a valid amount
            if update.new_status == "APPROVED":
                if update.approved_amount is None:
                    raise HTTPException(status_code=400,
                                        detail="approved_amount is required when approving")
                if update.approved_amount > claim["claimed_amount"]:
                    raise HTTPException(status_code=400,
                                        detail="Approved amount cannot exceed claimed amount")

            # Rule 3: rejection needs a reason
            if update.new_status == "REJECTED" and not update.rejection_reason:
                raise HTTPException(status_code=400,
                                    detail="rejection_reason is required when rejecting")

            cur.execute(
                """
                UPDATE claims
                SET status           = %s,
                    approved_amount  = COALESCE(%s, approved_amount),
                    rejection_reason = COALESCE(%s, rejection_reason),
                    settled_date     = CASE WHEN %s = 'PAID' THEN CURRENT_DATE
                                            ELSE settled_date END
                WHERE claim_id = %s
                RETURNING claim_number, status, approved_amount,
                          rejection_reason, settled_date
                """,
                (update.new_status, update.approved_amount, update.rejection_reason,
                 update.new_status, claim["claim_id"]),
            )
            updated = cur.fetchone()
        conn.commit()
    finally:
        conn.close()

    return updated