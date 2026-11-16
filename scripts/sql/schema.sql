-- pgAdmin connects you as "postgres". Switch to the project user so
-- claims_user OWNS these tables (otherwise the app can't access them later).
SET ROLE claims_user;

CREATE TABLE policyholders (
    policyholder_id  SERIAL PRIMARY KEY,
    full_name        VARCHAR(100) NOT NULL,
    date_of_birth    DATE NOT NULL,
    gender           VARCHAR(10) CHECK (gender IN ('MALE', 'FEMALE', 'OTHER')),
    email            VARCHAR(150) UNIQUE,
    phone            VARCHAR(15),
    city             VARCHAR(50),
    created_at       TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE policies (
    policy_id        SERIAL PRIMARY KEY,
    policy_number    VARCHAR(20) UNIQUE NOT NULL,
    policyholder_id  INT NOT NULL REFERENCES policyholders(policyholder_id),
    policy_type      VARCHAR(20) NOT NULL
                     CHECK (policy_type IN ('LIFE', 'HEALTH', 'CRITICAL_ILLNESS')),
    sum_assured      NUMERIC(12,2) NOT NULL CHECK (sum_assured > 0),
    annual_premium   NUMERIC(10,2) NOT NULL CHECK (annual_premium > 0),
    start_date       DATE NOT NULL,
    end_date         DATE NOT NULL,
    status           VARCHAR(15) NOT NULL DEFAULT 'ACTIVE'
                     CHECK (status IN ('ACTIVE', 'LAPSED', 'EXPIRED', 'CANCELLED')),
    CHECK (end_date > start_date)
);

CREATE TABLE claims (
    claim_id          SERIAL PRIMARY KEY,
    claim_number      VARCHAR(20) UNIQUE NOT NULL,
    policy_id         INT NOT NULL REFERENCES policies(policy_id),
    claim_type        VARCHAR(20) NOT NULL
                      CHECK (claim_type IN ('HOSPITALIZATION', 'OUTPATIENT', 'CRITICAL_ILLNESS', 'DEATH')),
    incident_date     DATE NOT NULL,
    submitted_date    DATE NOT NULL DEFAULT CURRENT_DATE,
    claimed_amount    NUMERIC(12,2) NOT NULL CHECK (claimed_amount > 0),
    approved_amount   NUMERIC(12,2) CHECK (approved_amount >= 0),
    status            VARCHAR(15) NOT NULL DEFAULT 'SUBMITTED'
                      CHECK (status IN ('SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'PAID')),
    rejection_reason  TEXT,
    settled_date      DATE,
    CHECK (submitted_date >= incident_date)
);

-- Speeds up joins and lookups on foreign keys
CREATE INDEX idx_policies_holder ON policies(policyholder_id);
CREATE INDEX idx_claims_policy   ON claims(policy_id);