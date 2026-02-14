import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL")
if not url:
    print("Error: DATABASE_URL not found in .env")
    exit(1)

print(f"Testing connection to: {url}")

try:
    conn = psycopg2.connect(url)
    print("SUCCESS: Connection established!")
    cur = conn.cursor()
    cur.execute("SELECT version();")
    ver = cur.fetchone()[0]
    print(f"Database version: {ver}")
    cur.close()
    conn.close()
except Exception as e:
    print(f"FAILED: {e}")
