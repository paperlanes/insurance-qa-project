# Insurance Claims QA & Analytics Platform

An end-to-end project on a Life & Health insurance claims system: database design,
SQL analytics, a claims API with business-rule validation, automated testing,
and a BI dashboard.

## Problem
Claims systems without proper validation pay out invalid claims. In the seeded
dataset, **19 of 23 invalid claims (~83%)** — incidents after policy expiry and
claims exceeding the sum assured — were approved or paid. This project detects
those defects with SQL validation checks and prevents them with API-level rules
and automated tests.

## Tech Stack
PostgreSQL · Python · Faker · FastAPI · Pytest · Power BI

## Project Status
| Phase | Description | Status |
|---|---|---|
| 1 | Database design, synthetic data, SQL analysis & validation | ✅ Done |
| 2 | FastAPI claims API with business rules | ⏳ In progress |
| 3 | Pytest API tests + automated data validation | 🔜 Planned |
| 4 | Power BI dashboard | 🔜 Planned |

## Database Design
Three normalized tables: `policyholders` → `policies` → `claims` (one-to-many).
- Foreign keys enforce referential integrity
- CHECK constraints block invalid values (negative amounts, end date before start)
- Cross-table rules (e.g. claim after policy expiry) are validated in the
  application layer and by SQL checks — not by the database

Schema: [`sql/schema.sql`](sql/schema.sql)

## Synthetic Data
`scripts/generate_data.py` generates ~1,000 policyholders, ~1,500 policies and
~2,000 claims with realistic business logic (claim types match policy types,
statuses follow dates, partial approvals for health claims).
It also **deliberately seeds ~3% defective claims** to test the validation layer.

## SQL Analysis — [`sql/analysis.sql`](sql/analysis.sql)
- Claims pipeline breakdown by status
- Approval rate by policy type
- Settlement speed by claim type
- Top cities by payout
- Month-over-month claim trends (`LAG`)
- Customer payout ranking (`RANK` / `DENSE_RANK`)
- Running total of payouts
- Top 3 claims per policy type (`ROW_NUMBER` + `PARTITION BY`)
- Loss ratio by product (avoiding join fan-out with separate CTEs)

## Data Validation — [`sql/validation.sql`](sql/validation.sql)
| Check | Defects found |
|---|---|
| Incident after policy end date | 18 |
| Claimed amount exceeds sum assured | 5 |
| Invalid claims approved or paid | 19 |

## How to Run
1. Create a PostgreSQL database `insurance_claims` and run `sql/schema.sql`
2. `python -m venv venv` and activate it
3. `pip install -r requirements.txt`
4. Create a `.env` file with `DB_PASSWORD=your_password`
5. `python scripts/generate_data.py`