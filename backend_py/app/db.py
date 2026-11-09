"""PostgreSQL access layer (psycopg 3) mirroring JdbcTemplate semantics.

The pool is created lazily so that unit tests never need a database, and every
method turns connection errors into exceptions the caller catches (all Java
call sites wrap these in try/catch for fallback behavior).
"""

import threading
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg
from psycopg import Connection
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, host: str, port: int, dbname: str, user: str, password: str):
        self._lock = threading.Lock()
        self._pool: ConnectionPool | None = None
        self._conninfo = psycopg.conninfo.make_conninfo(
            host=host, port=port, dbname=dbname, user=user, password=password,
            connect_timeout=3,
            options="-c timezone=UTC",
        )

    @property
    def pool(self) -> ConnectionPool:
        with self._lock:
            if self._pool is None:
                self._pool = ConnectionPool(
                    self._conninfo,
                    min_size=1,
                    max_size=8,
                    open=True,
                    kwargs={"row_factory": dict_row},
                )
            return self._pool

    def close(self) -> None:
        with self._lock:
            if self._pool is not None:
                self._pool.close()
                self._pool = None

    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self.pool.connection() as conn:
            cur = conn.execute(psycopg.sql.SQL(sql), params)
            return cur.fetchall()

    def query_one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def query_list(self, sql: str, params: tuple | list = (), field: str | None = None) -> list[Any]:
        """Scalar column list (user only needs one value per row)."""
        rows = self.query(sql, params)
        if field is not None:
            return [row[field] for row in rows]
        return [next(iter(row.values())) for row in rows]

    def scalar(self, sql: str, params: tuple | list = ()) -> Any:
        row = self.query_one(sql, params)
        if row is None:
            return None
        return next(iter(row.values()))

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        with self.pool.connection() as conn:
            cur = conn.execute(psycopg.sql.SQL(sql), params)
            return cur.rowcount

    def execute_returning(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        with self.pool.connection() as conn:
            cur = conn.execute(psycopg.sql.SQL(sql), params)
            return cur.fetchone()

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        """One connection dedicated to a transaction (Spring @Transactional)."""
        with self.pool.connection() as conn:
            try:
                yield conn
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()
