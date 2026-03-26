from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import settings


pool = ConnectionPool(
    conninfo=settings.database_url,
    min_size=1,
    max_size=10,
    kwargs={"row_factory": dict_row, "autocommit": False},
    open=False,
)


def open_pool() -> None:
    last_error = None

    if not pool.closed:
        return

    for attempt in range(1, 16):
        try:
            pool.open(wait=True)

            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")

            print(f"[DB] pool ready (attempt={attempt})")
            return

        except Exception as e:
            last_error = e
            print(f"[DB] connect retry {attempt}/15 failed: {e}")

            try:
                if not pool.closed:
                    pool.close()
            except Exception:
                pass

            time.sleep(2)

    raise RuntimeError(f"database connection failed after retries: {last_error}")


def close_pool() -> None:
    if not pool.closed:
        pool.close()


@contextmanager
def get_conn() -> Iterator:
    open_pool()
    with pool.connection() as conn:
        yield conn
