-- V1: Claims where the incident happened AFTER the policy ended
SELECT c.claim_number, p.policy_number, p.end_date, c.incident_date, c.status
FROM claims c
JOIN policies p ON p.policy_id = c.policy_id
WHERE c.incident_date > p.end_date;

-- V2: Claims asking for more than the policy's sum assured
SELECT c.claim_number, p.policy_number, p.sum_assured, c.claimed_amount, c.status
FROM claims c
JOIN policies p ON p.policy_id = c.policy_id
WHERE c.claimed_amount > p.sum_assured;

-- V3: Approved/paid claims that SHOULD have been rejected (the serious ones)
SELECT c.claim_number, c.status, c.approved_amount,
       CASE
           WHEN c.incident_date > p.end_date      THEN 'Incident after policy expiry'
           WHEN c.claimed_amount > p.sum_assured  THEN 'Claim exceeds sum assured'
       END AS issue
FROM claims c
JOIN policies p ON p.policy_id = c.policy_id
WHERE c.status IN ('APPROVED', 'PAID')
  AND (c.incident_date > p.end_date OR c.claimed_amount > p.sum_assured);