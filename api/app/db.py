"""Postgres access: one pool, dict rows, explicit transactions."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

logger = logging.getLogger("omr.db")

_pool: ConnectionPool | None = None


def pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        # Small pool: Neon's pooler endpoint multiplexes server-side, and a
        # phone-facing API is bursty rather than concurrent.
        #
        # check=check_connection: Neon suspends/closes idle connections on its
        # own schedule, and the pool does not otherwise notice until a query
        # fails on a connection it just handed out. The check pings before
        # handing one over, so a dead connection is replaced rather than
        # returned -- this is what was producing "server closed the
        # connection unexpectedly" after the app sat idle for a while.
        # max_idle: recycle a connection that has sat unused rather than wait
        # for it to go stale.
        _pool = ConnectionPool(config.DATABASE_URL, min_size=1, max_size=8,
                               kwargs={"row_factory": dict_row},
                               check=ConnectionPool.check_connection,
                               max_idle=180, open=True)
    return _pool


@contextmanager
def conn():
    """A connection in a transaction: commits on success, rolls back on error."""
    with pool().connection() as c:
        yield c


def _retrying(fn):
    """Run *fn(connection)* once, retrying exactly once on a dead connection.

    The pool's health check (see `pool()`) catches most of this before a
    connection is ever handed out, but one already in a caller's hand when
    Neon drops it still fails on first use. That failure is a transport
    error, not a data problem, so one clean retry on a fresh connection is
    the right response -- surfacing it as a 500 would be wrong for something
    this routine.
    """
    try:
        with conn() as c:
            return fn(c)
    except psycopg.OperationalError:
        logger.warning("database connection dropped; retrying once")
        with conn() as c:
            return fn(c)


def query(sql: str, params: tuple = ()) -> list[dict]:
    return _retrying(lambda c: c.execute(sql, params).fetchall())


def one(sql: str, params: tuple = ()) -> dict | None:
    return _retrying(lambda c: c.execute(sql, params).fetchone())


def execute(sql: str, params: tuple = ()) -> dict | None:
    """Run a statement; returns the first row when the SQL has RETURNING."""
    def run(c):
        cur = c.execute(sql, params)
        return cur.fetchone() if cur.description else None
    return _retrying(run)


def init_schema() -> None:
    sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    with conn() as c:
        c.execute(sql)


def audit(c, user_id: int | None, action: str, entity: str | None = None,
          entity_id: int | None = None, detail: dict | None = None) -> None:
    """Append an audit row on an existing connection/transaction.

    Takes the connection rather than opening its own so the log entry commits
    or rolls back with the change it describes.
    """
    import json
    c.execute(
        "INSERT INTO audit_log (user_id, action, entity, entity_id, detail)"
        " VALUES (%s,%s,%s,%s,%s)",
        (user_id, action, entity, entity_id, json.dumps(detail or {})))
