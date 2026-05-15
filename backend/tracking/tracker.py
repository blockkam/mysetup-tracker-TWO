from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime


DB_PATH = (
    Path(__file__)
    .resolve()
    .parent / "trades.db"
)


# ============================================================
# CONNECT DB
# ============================================================

def get_conn():

    return sqlite3.connect(DB_PATH)


# ============================================================
# INIT DATABASE
# ============================================================

def init_db():

    conn = get_conn()

    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trades (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            created_at TEXT,

            symbol TEXT,
            side TEXT,

            grade TEXT,

            entry REAL,
            sl REAL,

            tp1 REAL,
            tp2 REAL,
            tp3 REAL,

            rr1 REAL,
            rr2 REAL,
            rr3 REAL,

            score REAL,

            setup_type TEXT,

            status TEXT,

            result TEXT,

            pnl REAL
        )
        """
    )

    conn.commit()

    conn.close()


# ============================================================
# SAVE SIGNAL
# ============================================================

def save_signal(signal: dict):

    conn = get_conn()

    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO trades (

            created_at,

            symbol,
            side,

            grade,

            entry,
            sl,

            tp1,
            tp2,
            tp3,

            rr1,
            rr2,
            rr3,

            score,

            setup_type,

            status,

            result,

            pnl

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.utcnow().isoformat(),

            signal["symbol"],
            signal["side"],

            signal["grade"],

            signal["entry"],
            signal["sl"],

            signal["tp1"],
            signal["tp2"],
            signal["tp3"],

            signal["rr1"],
            signal["rr2"],
            signal["rr3"],

            signal["score"],

            signal["setup_type"],

            "OPEN",

            None,

            0.0,
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# FETCH OPEN TRADES
# ============================================================

def fetch_open_trades():

    conn = get_conn()

    conn.row_factory = sqlite3.Row

    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM trades
        WHERE status = 'OPEN'
        """
    )

    rows = cur.fetchall()

    conn.close()

    return [dict(r) for r in rows]


# ============================================================
# CLOSE TRADE
# ============================================================

def close_trade(
    trade_id: int,
    result: str,
    pnl: float,
):

    conn = get_conn()

    cur = conn.cursor()

    cur.execute(
        """
        UPDATE trades

        SET
            status = 'CLOSED',
            result = ?,
            pnl = ?

        WHERE id = ?
        """,
        (
            result,
            pnl,
            trade_id,
        ),
    )

    conn.commit()

    conn.close()


# ============================================================
# STATS
# ============================================================

def get_stats():

    conn = get_conn()

    cur = conn.cursor()

    # total trades
    cur.execute(
        "SELECT COUNT(*) FROM trades"
    )

    total = cur.fetchone()[0]

    # wins
    cur.execute(
        """
        SELECT COUNT(*)
        FROM trades
        WHERE result = 'WIN'
        """
    )

    wins = cur.fetchone()[0]

    # losses
    cur.execute(
        """
        SELECT COUNT(*)
        FROM trades
        WHERE result = 'LOSS'
        """
    )

    losses = cur.fetchone()[0]

    # pnl
    cur.execute(
        """
        SELECT SUM(pnl)
        FROM trades
        """
    )

    pnl = cur.fetchone()[0]

    pnl = pnl if pnl else 0.0

    conn.close()

    winrate = 0

    if total > 0:

        winrate = round(
            (wins / total) * 100,
            2,
        )

    return {
        "total_trades": total,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "pnl": round(pnl, 2),
    }


# ============================================================
# INIT ON IMPORT
# ============================================================

init_db()