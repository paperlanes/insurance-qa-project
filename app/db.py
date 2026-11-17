import os

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Open a new connection to the claims database."""
    return psycopg2.connect(
        host="localhost",
        port=5432,
        dbname="insurance_claims",
        user="claims_user",
        password=os.getenv("DB_PASSWORD"),
        cursor_factory=RealDictCursor,
    )