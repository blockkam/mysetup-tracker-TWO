"""Background resolver — pulls Binance fapi 15m klines for OPEN signals
and updates MFE / MAE / status / result_r.

Pricing model (equal 1/3 scale-out):
  STOPPED (no TPs hit)          → result_r = -1.0
  BE_STOP (stopped at entry)    → result_r =  rr1 / 3
  TP2_TRAIL (stopped at TP1)    → result_r = (rr1 + rr2) / 3
  TP3 (all hit)                 → result_r = (rr1 + rr2 + rr3) / 3
  EXPIRED                       → result_r = sum of realized partials only

Key fix vs original: within a single bar, TPs are evaluated BEFORE the SL
check so that a bar whose high touches TP1 and whose low touches the old SL
correctly moves the stop to break-even first, then re-tests the low against
the new (BE) stop — instead of firing the raw SL and missing the TP entirely.

MAE convention: stored as a negative R value (adverse excursion below zero).
MFE convention: stored as a positive R value (favorable excursion above zero).
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from binance_client import fetch_klines

log = logging.getLogger("resolver")

EXPIRY_BARS    = int(os.environ.get("SIGNAL_EXPIRY_BARS", 96))
MAX_CONCURRENT = int(os.environ.get("RESOLVER_CONCURRENCY", 12))  # fix #4
FETCH_TIMEOUT  = float(os.environ.get("RESOLVER_TIMEOUT_S", 20))  # fix #5
BATCH_SIZE     = int(os.environ.get("RESOLVER_BATCH_SIZE", 200))  # fix #6

# fix #4 — semaphore lives at module level, created lazily
_SEM: Optional[asyncio.Semaphore] = None


def _sem() -> asyncio.Semaphore:
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(MAX_CONCURRENT)
    return _SEM


# ── helpers ──────────────────────────────────────────────────────────────────

def _iso_to_ms(iso: str) -> int:
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def _to_int_safe(value: Any, fallback: int = 0) -> int:
    """fix #7 — MongoDB may return last_resolved_open_time as float/Decimal128."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _partial_r(
    hit_tp1: bool, hit_tp2: bool, hit_tp3: bool,
    rr1: float,    rr2: float,    rr3: float,
) -> float:
    total = 0.0
    if hit_tp1: total += rr1 / 3.0
    if hit_tp2: total += rr2 / 3.0
    if hit_tp3: total += rr3 / 3.0
    return total


# ── resolve one signal ───────────────────────────────────────────────────────

async def _resolve_one(
    db,
    client: httpx.AsyncClient,
    sig:    Dict[str, Any],
) -> bool:
    """
    Fetch klines since last checkpoint and walk bar-by-bar.
    Returns True if the signal's status or MFE/MAE changed.
    """
    symbol = sig["symbol"]
    side   = sig["side"]
    entry  = float(sig["entry"])

    tp1 = float(sig["tp1"])
    tp2 = float(sig["tp2"])
    tp3 = float(sig["tp3"])

    rr1 = float(sig.get("rr1") or 0)
    rr2 = float(sig.get("rr2") or 0)
    rr3 = float(sig.get("rr3") or 0)

    # fix #1 — sl_initial may be missing on signals created before the field existed
    sl_initial_raw = sig.get("sl_initial") or sig.get("sl")
    if sl_initial_raw is None:
        log.warning("[SKIP] %s %s — missing sl_initial and sl", symbol, sig.get("id"))
        return False

    sl_initial = float(sl_initial_raw)
    risk_abs   = abs(entry - sl_initial)

    # fix #13 — log instead of silently returning
    if risk_abs <= 0:
        log.warning("[SKIP] %s %s — risk_abs=0 (entry==sl_initial), cannot resolve", symbol, sig.get("id"))
        return False

    cur_sl      = float(sig.get("sl") or sl_initial)
    hit_tp1     = bool(sig.get("hit_tp1", False))
    hit_tp2     = bool(sig.get("hit_tp2", False))
    hit_tp3     = bool(sig.get("hit_tp3", False))
    mfe         = float(sig.get("max_favorable_r") or 0)
    mae         = float(sig.get("max_adverse_r")   or 0)
    bars_elapsed = int(sig.get("bars_elapsed")     or 0)
    bars_to_tp1  = sig.get("bars_to_tp1")
    bars_to_tp2  = sig.get("bars_to_tp2")
    bars_to_tp3  = sig.get("bars_to_tp3")

    # fix #7 — safely convert last_resolved_open_time to int
    last_ot  = sig.get("last_resolved_open_time")
    start_ms = (_to_int_safe(last_ot) + 1) if last_ot is not None else _iso_to_ms(sig["created_at"])

    # fix #8 — if your fetch_klines doesn't accept start_ms, add it to binance_client.py:
    #   async def fetch_klines(client, symbol, interval, limit=500, start_ms=None)
    #   and pass startTime=start_ms in the query params when it's not None.
    klines = await fetch_klines(client, symbol, "15m", start_ms=start_ms, limit=500)
    if not klines:
        return False

    status         = sig["status"]
    last_open_time = last_ot
    prev_mfe       = mfe
    prev_mae       = mae

    for k in klines:
        open_time = int(k[0])
        high      = float(k[2])
        low       = float(k[3])
        last_open_time = open_time
        bars_elapsed  += 1

        # ── MFE / MAE ───────────────────────────────────────
        if side == "LONG":
            mfe = max(mfe,  (high - entry) / risk_abs)
            mae = min(mae,  (low  - entry) / risk_abs)   # negative = adverse
        else:
            mfe = max(mfe,  (entry - low)  / risk_abs)
            mae = min(mae,  (entry - high) / risk_abs)   # negative = adverse

        # ── fix #2: evaluate TPs BEFORE SL on the same bar ──
        #
        # Original code checked SL first, which meant a bar whose high hit TP1
        # and whose low hit the old SL would fire the stop and miss the TP.
        # Correct simulation: if high reached TP1, the SL has already moved to
        # break-even — THEN we re-test the low against the new SL.
        #
        if side == "LONG":
            if not hit_tp1 and high >= tp1:
                hit_tp1     = True
                bars_to_tp1 = bars_elapsed
                cur_sl      = max(cur_sl, entry)   # move SL to break-even
            if hit_tp1 and not hit_tp2 and high >= tp2:
                hit_tp2     = True
                bars_to_tp2 = bars_elapsed
                cur_sl      = max(cur_sl, tp1)     # trail SL to TP1
            if hit_tp2 and not hit_tp3 and high >= tp3:
                hit_tp3     = True
                bars_to_tp3 = bars_elapsed
                status      = "TP3"
                break

        else:  # SHORT
            if not hit_tp1 and low <= tp1:
                hit_tp1     = True
                bars_to_tp1 = bars_elapsed
                cur_sl      = min(cur_sl, entry)   # BE
            if hit_tp1 and not hit_tp2 and low <= tp2:
                hit_tp2     = True
                bars_to_tp2 = bars_elapsed
                cur_sl      = min(cur_sl, tp1)     # trail to TP1
            if hit_tp2 and not hit_tp3 and low <= tp3:
                hit_tp3     = True
                bars_to_tp3 = bars_elapsed
                status      = "TP3"
                break

        # ── SL check (against updated cur_sl) ───────────────
        stopped = (
            (side == "LONG"  and low  <= cur_sl) or
            (side == "SHORT" and high >= cur_sl)
        )

        if stopped:
            if hit_tp2:
                status = "TP2_TRAIL"    # fix #11 — was "TP2", misleading name
            elif hit_tp1:
                status = "BE_STOP"
            else:
                status = "STOPPED"
            break

        # ── expiry ──────────────────────────────────────────
        if bars_elapsed >= EXPIRY_BARS:
            status = "EXPIRED"
            break

    # ── compute result_r ────────────────────────────────────
    result_r: Optional[float] = None

    if status == "STOPPED":
        result_r = -1.0

    elif status == "BE_STOP":
        # fix #3 — original had dead `elif status in ("BE_STOP", "TP1")` branch.
        # "TP1" is never set as a status; removed. BE_STOP always means hit_tp1=True
        # because the SL can only move to BE after TP1 is tagged.
        result_r = rr1 / 3.0

    elif status == "TP2_TRAIL":
        result_r = _partial_r(hit_tp1, hit_tp2, False, rr1, rr2, rr3)

    elif status == "TP3":
        result_r = _partial_r(True, True, True, rr1, rr2, rr3)

    elif status == "EXPIRED":
        result_r = _partial_r(hit_tp1, hit_tp2, hit_tp3, rr1, rr2, rr3)
        # EXPIRED with zero result_r and no partials = full -1R by convention
        if result_r == 0.0:
            result_r = -1.0

    # ── build update doc ────────────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()

    update: Dict[str, Any] = {
        "sl":                       cur_sl,
        "hit_tp1":                  hit_tp1,
        "hit_tp2":                  hit_tp2,
        "hit_tp3":                  hit_tp3,
        "bars_to_tp1":              bars_to_tp1,
        "bars_to_tp2":              bars_to_tp2,
        "bars_to_tp3":              bars_to_tp3,
        "bars_elapsed":             bars_elapsed,
        "max_favorable_r":          round(mfe, 4),
        "max_adverse_r":            round(mae, 4),
        "status":                   status,
        "updated_at":               now_iso,
        "last_resolved_open_time":  last_open_time,
    }

    if status != "OPEN" and result_r is not None:
        update["result_r"]    = round(result_r, 4)
        update["resolved_at"] = now_iso

    await db.signals.update_one({"id": sig["id"]}, {"$set": update})

    changed = (status != sig["status"] or mfe != prev_mfe or mae != prev_mae)
    return changed


# ── semaphore wrapper ────────────────────────────────────────────────────────

async def _resolve_one_safe(
    db,
    client: httpx.AsyncClient,
    sig:    Dict[str, Any],
) -> bool:
    async with _sem():
        try:
            return await _resolve_one(db, client, sig)
        except Exception:
            log.exception("[RESOLVE ERROR] %s", sig.get("symbol"))
            return False


# ── public entry point ───────────────────────────────────────────────────────

async def resolve_open_signals(db) -> int:
    """
    Iterate every OPEN signal and update it.

    Returns the count of signals iterated.
    Processes in batches of BATCH_SIZE (fix #6) so RAM usage is bounded.
    Uses asyncio.gather + semaphore for concurrent resolution (fix #4).
    Uses a single httpx.AsyncClient with a per-request timeout (fix #5).
    """
    total_iterated = 0
    total_changed  = 0
    skip           = 0

    # fix #5 — shared client with explicit timeout for the whole resolver run
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:

        while True:
            # fix #6 — pull a batch instead of loading all 5000 at once
            batch: List[Dict[str, Any]] = await (
                db.signals
                  .find({"status": "OPEN"}, {"_id": 0})
                  .skip(skip)
                  .limit(BATCH_SIZE)
                  .to_list(BATCH_SIZE)
            )

            if not batch:
                break

            # fix #4 — resolve batch concurrently under semaphore
            results = await asyncio.gather(
                *[_resolve_one_safe(db, client, sig) for sig in batch]
            )

            total_iterated += len(batch)
            total_changed  += sum(results)
            skip           += len(batch)

            # short circuit if we got a partial batch (last page)
            if len(batch) < BATCH_SIZE:
                break

    # fix #12 — log actual outcome counts so you can see resolver activity
    log.info(
        "resolver: iterated=%d  changed=%d  unchanged=%d",
        total_iterated,
        total_changed,
        total_iterated - total_changed,
    )

    return total_iterated