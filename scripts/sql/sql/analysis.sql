-- Q1: Claim count and share by status
SELECT
    status,
    COUNT(*) AS claim_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_total
FROM claims
GROUP BY status
ORDER BY claim_count DESC;

-- Q2: Approval rate by policy type (decided claims only)
SELECT
    p.policy_type,
    COUNT(*) AS decided_claims,
    COUNT(*) FILTER (WHERE c.status IN ('APPROVED', 'PAID')) AS approved_claims,
    ROUND(100.0 * COUNT(*) FILTER (WHERE c.status IN ('APPROVED', 'PAID')) / COUNT(*), 1) AS approval_rate_pct
FROM claims c
JOIN policies p ON p.policy_id = c.policy_id
WHERE c.status IN ('APPROVED', 'PAID', 'REJECTED')
GROUP BY p.policy_type
ORDER BY approval_rate_pct DESC;

-- Q3: Settlement speed by claim type (paid claims only)
SELECT
    claim_type,
    COUNT(*) AS paid_claims,
    ROUND(AVG(settled_date - submitted_date), 1) AS avg_days_to_settle,
    MIN(settled_date - submitted_date) AS fastest,
    MAX(settled_date - submitted_date) AS slowest
FROM claims
WHERE status = 'PAID'
GROUP BY claim_type
ORDER BY avg_days_to_settle;

-- Q4: Top 10 cities by total approved payout
SELECT
    ph.city,
    COUNT(c.claim_id) AS claims,
    SUM(c.approved_amount) AS total_approved,
    ROUND(AVG(c.approved_amount), 0) AS avg_approved
FROM claims c
JOIN policies p       ON p.policy_id = c.policy_id
JOIN policyholders ph ON ph.policyholder_id = p.policyholder_id
WHERE c.status IN ('APPROVED', 'PAID')
GROUP BY ph.city
ORDER BY total_approved DESC
LIMIT 10;

-- Q5: Monthly claim volume with month-over-month change
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', submitted_date)::date AS month,
        COUNT(*) AS claims
    FROM claims
    GROUP BY 1
)
SELECT
    month,
    claims,
    LAG(claims) OVER (ORDER BY month) AS prev_month,
    claims - LAG(claims) OVER (ORDER BY month) AS change,
    ROUND(100.0 * (claims - LAG(claims) OVER (ORDER BY month))
          / LAG(claims) OVER (ORDER BY month), 1) AS pct_change
FROM monthly
ORDER BY month;

-- Q6: Rank customers by total approved payout
WITH customer_payouts AS (
    SELECT
        ph.policyholder_id,
        ph.full_name,
        SUM(c.approved_amount) AS total_paid
    FROM claims c
    JOIN policies p       ON p.policy_id = c.policy_id
    JOIN policyholders ph ON ph.policyholder_id = p.policyholder_id
    WHERE c.status IN ('APPROVED', 'PAID')
    GROUP BY ph.policyholder_id, ph.full_name
)
SELECT
    full_name,
    total_paid,
    ROW_NUMBER() OVER (ORDER BY total_paid DESC) AS row_num,
    RANK()       OVER (ORDER BY total_paid DESC) AS rnk,
    DENSE_RANK() OVER (ORDER BY total_paid DESC) AS dense_rnk
FROM customer_payouts
ORDER BY total_paid DESC
LIMIT 15;

-- Q7: Monthly payouts with cumulative running total
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', settled_date)::date AS month,
        SUM(approved_amount) AS paid_this_month
    FROM claims
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    month,
    paid_this_month,
    SUM(paid_this_month) OVER (ORDER BY month) AS running_total
FROM monthly
ORDER BY month;

-- Q8: Top 3 largest claims within each policy type
WITH ranked AS (
    SELECT
        c.claim_number,
        p.policy_type,
        c.claimed_amount,
        c.status,
        ROW_NUMBER() OVER (
            PARTITION BY p.policy_type
            ORDER BY c.claimed_amount DESC
        ) AS rn
    FROM claims c
    JOIN policies p ON p.policy_id = c.policy_id
)
SELECT policy_type, claim_number, claimed_amount, status
FROM ranked
WHERE rn <= 3
ORDER BY policy_type, rn;

-- Q9: Loss ratio by policy type (approximate)
WITH premiums AS (
    -- Premium earned = annual premium × years the policy has run so far
    SELECT
        policy_type,
        SUM(annual_premium * (LEAST(end_date, CURRENT_DATE) - start_date) / 365.0) AS premium_earned
    FROM policies
    GROUP BY policy_type
),
payouts AS (
    SELECT
        p.policy_type,
        SUM(c.approved_amount) AS total_paid
    FROM claims c
    JOIN policies p ON p.policy_id = c.policy_id
    WHERE c.status IN ('APPROVED', 'PAID')
    GROUP BY p.policy_type
)
SELECT
    pr.policy_type,
    ROUND(pr.premium_earned, 0) AS premium_earned,
    COALESCE(pa.total_paid, 0)  AS total_paid,
    ROUND(100.0 * COALESCE(pa.total_paid, 0) / pr.premium_earned, 1) AS loss_ratio_pct
FROM premiums pr
LEFT JOIN payouts pa ON pa.policy_type = pr.policy_type
ORDER BY loss_ratio_pct DESC;


