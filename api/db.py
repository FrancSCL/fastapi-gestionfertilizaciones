import os
import pymysql
import pymysql.cursors
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


def _config() -> dict:
    cfg = {
        "user": os.getenv("MYSQL_USER"),
        "password": os.getenv("MYSQL_PASSWORD"),
        "database": os.getenv("MYSQL_DB"),
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
        "connect_timeout": 10,
    }
    # En Cloud Run (K_SERVICE presente) + Cloud SQL vinculado via socket.
    instance = os.getenv("INSTANCE_CONNECTION_NAME")
    if os.getenv("K_SERVICE") and instance:
        cfg["unix_socket"] = f"/cloudsql/{instance}"
    else:
        cfg["host"] = os.getenv("MYSQL_HOST")
        cfg["port"] = int(os.getenv("MYSQL_PORT", 3306))
    return cfg


@contextmanager
def get_connection():
    conn = pymysql.connect(**_config())
    try:
        yield conn
    finally:
        conn.close()
