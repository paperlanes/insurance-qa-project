import os
import random
from datetime import date, timedelta

import psycopg2
from dotenv import load_dotenv
from faker import Faker

load_dotenv()                # reads .env into environment variables
fake = Faker("en_IN")        # Indian names, cities, phone numbers
Faker.seed(42)               # same seed = same data every run (reproducible)
random.seed(42)

TODAY = date.today()
NUM_POLICYHOLDERS = 1000

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="insurance_claims",
    user="claims_user",
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor()

# Empty the tables first so the script can be re-run safely.
# RESTART IDENTITY resets the SERIAL counters back to 1.
cur.execute("TRUNCATE claims, policies, policyholders RESTART IDENTITY")


def random_date(start, end):
    """Random date between start and end (inclusive)."""
    return start + timedelta(days=random.randint(0, (end - start).days))


# ---------- 1. Policyholders ----------
holder_ids = []
for _ in range(NUM_POLICYHOLDERS):
    cur.execute(
        """
        INSERT INTO policyholders (full_name, date_of_birth, gender, email, phone, city)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING policyholder_id
        """,
        (
            fake.name(),
            fake.date_of_birth(minimum_age=18, maximum_age=70),
            random.choices(["MALE", "FEMALE", "OTHER"], weights=[48, 48, 4])[0],
            fake.unique.email(),
            fake.phone_number()[:15],
            fake.city(),
        ),
    )
    holder_ids.append(cur.fetchone()[0])


# ---------- 2. Policies ----------
# Realistic ranges per policy type (amounts in INR)
POLICY_CONFIG = {
    "HEALTH":           {"sum": (300_000, 2_500_000),    "rate": (0.02, 0.04),   "years": (1, 1)},
    "LIFE":             {"sum": (2_500_000, 20_000_000), "rate": (0.003, 0.008), "years": (10, 30)},
    "CRITICAL_ILLNESS": {"sum": (1_000_000, 5_000_000),  "rate": (0.01, 0.02),   "years": (5, 20)},
}

policies = []
policy_counter = 1
for holder_id in holder_ids:
    num_policies = random.choices([1, 2, 3], weights=[60, 30, 10])[0]
    for _ in range(num_policies):
        ptype = random.choices(list(POLICY_CONFIG), weights=[60, 25, 15])[0]
        cfg = POLICY_CONFIG[ptype]

        sum_assured = round(random.randint(*cfg["sum"]), -4)          # nearest 10,000
        premium = round(sum_assured * random.uniform(*cfg["rate"]), 2)
        start = random_date(date(2019, 1, 1), TODAY - timedelta(days=30))
        end = start + timedelta(days=365 * random.randint(*cfg["years"]))

        if end < TODAY:
            status = "EXPIRED"
        else:
            status = random.choices(["ACTIVE", "LAPSED", "CANCELLED"], weights=[85, 10, 5])[0]

        cur.execute(
            """
            INSERT INTO policies (policy_number, policyholder_id, policy_type, sum_assured,
                                  annual_premium, start_date, end_date, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING policy_id
            """,
            (f"POL{policy_counter:06d}", holder_id, ptype, sum_assured,
             premium, start, end, status),
        )
        policies.append({"id": cur.fetchone()[0], "type": ptype,
                         "sum": sum_assured, "start": start, "end": end})
        policy_counter += 1


# ---------- 3. Claims ----------
# How many claims each policy type tends to get: (options, weights)
CLAIMS_PER_POLICY = {
    "HEALTH":           ([0, 1, 2, 3], [40, 35, 15, 10]),
    "LIFE":             ([0, 1], [95, 5]),
    "CRITICAL_ILLNESS": ([0, 1], [80, 20]),
}
REJECTION_REASONS = [
    "Pre-existing condition not disclosed",
    "Treatment not covered under policy",
    "Incomplete documentation",
    "Claim filed after waiting period",
    "Policy not active on incident date",
]

claim_counter = 1
for p in policies:
    options, weights = CLAIMS_PER_POLICY[p["type"]]
    for _ in range(random.choices(options, weights=weights)[0]):

        # Incident happens while the policy is in force...
        incident = random_date(p["start"], min(p["end"], TODAY))
        # ...EXCEPT ~2% deliberately bad rows: incident AFTER the policy expired
        if random.random() < 0.02 and p["end"] < TODAY - timedelta(days=10):
            incident = random_date(p["end"] + timedelta(days=1), TODAY)

        submitted = min(incident + timedelta(days=random.randint(0, 30)), TODAY)

        # Claim type and amount depend on the policy type
        if p["type"] == "HEALTH":
            ctype = random.choices(["HOSPITALIZATION", "OUTPATIENT"], weights=[60, 40])[0]
            if ctype == "HOSPITALIZATION":
                amount = min(round(random.randint(20_000, 500_000), -2), p["sum"])
                # ~1% deliberately bad rows: claim exceeds sum assured
                if random.random() < 0.01:
                    amount = round(p["sum"] * random.uniform(1.1, 1.5), -2)
            else:
                amount = round(random.randint(500, 15_000), -2)
        elif p["type"] == "LIFE":
            ctype, amount = "DEATH", p["sum"]
        else:
            ctype, amount = "CRITICAL_ILLNESS", p["sum"]

        # Status: recent claims are still in progress, older ones are decided
        approved_amount = rejection_reason = settled = None
        if (TODAY - submitted).days < 30:
            status = random.choice(["SUBMITTED", "UNDER_REVIEW"])
        else:
            status = random.choices(["APPROVED", "PAID", "REJECTED"], weights=[15, 60, 25])[0]

        if status in ("APPROVED", "PAID"):
            # Lump-sum products pay in full; health claims often get partially approved
            if ctype in ("DEATH", "CRITICAL_ILLNESS"):
                approved_amount = amount
            else:
                approved_amount = round(amount * random.uniform(0.7, 1.0), -2)
        if status == "PAID":
            settled = min(submitted + timedelta(days=random.randint(5, 60)), TODAY)
        if status == "REJECTED":
            rejection_reason = random.choice(REJECTION_REASONS)

        cur.execute(
            """
            INSERT INTO claims (claim_number, policy_id, claim_type, incident_date,
                                submitted_date, claimed_amount, approved_amount,
                                status, rejection_reason, settled_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (f"CLM{claim_counter:06d}", p["id"], ctype, incident, submitted,
             amount, approved_amount, status, rejection_reason, settled),
        )
        claim_counter += 1

conn.commit()   # nothing is saved until this line runs
cur.close()
conn.close()

print(f"Inserted {len(holder_ids)} policyholders, {len(policies)} policies, "
      f"{claim_counter - 1} claims")