import os
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv
import psycopg

# Зчитування конфігурації з .env у корені проєкту
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", 5432)),
    "dbname": os.getenv("POSTGRES_DB", "cityflow_s08"),
    "user": os.getenv("POSTGRES_USER", "cityflow_user"),
    "password": os.getenv("POSTGRES_PASSWORD", "cityflow_pass"),
}

def get_connection():
    return psycopg.connect(**DB_CONFIG)

@contextmanager
def get_db_cursor(autocommit=False):
    with psycopg.connect(**DB_CONFIG, autocommit=autocommit) as conn:
        with conn.cursor() as cur:
            yield conn, cur
