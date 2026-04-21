import os
import pymysql
import pymysql.cursors
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor,
    "connect_timeout": 10,
}


@contextmanager
def get_connection():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()
