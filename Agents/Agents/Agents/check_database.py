import os
from dotenv import load_dotenv
import psycopg2

load_dotenv()

database_url = os.getenv("DATABASE_URL")

if not database_url:
    raise RuntimeError("DATABASE_URL not found in .env")

conn = psycopg2.connect(database_url)
cur = conn.cursor()

tables = [
    "companies",
    "company_research",
    "company_validation",
    "company_solutions",
    "final_rankings",
]

print()
print("=" * 60)
print("DATABASE VERIFICATION")
print("=" * 60)

for table in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table};")
        count = cur.fetchone()[0]
        print(f"{table}: {count}")
    except Exception as error:
        conn.rollback()
        print(f"{table}: ERROR - {error}")

cur.close()
conn.close()

print("=" * 60)
print("DATABASE CHECK COMPLETE")
print("=" * 60)