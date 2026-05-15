from __future__ import annotations

import asyncio
import logging
import random
import signal
import time
from datetime import datetime, timezone

import httpx
import pandas as pd

from binance_client import (
    fetch_klines,
    fetch_usdt_perp_symbols,
)
from strategy_v15 import build_signal
from tracking.tracker import save_signal


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)


# ============================================================
# CONFIG
# ============================================================

API_URL = "http://127.0.0.1:8001/api/signals"

SCAN_SYMBOLS_PER_CYCLE = 110
BATCH_SIZE = 8
BATCH_SLEEP = 2
SCAN_INTERVAL = 180
ALERT_COOLDOWN = 20 * 60
MAX_CONCURRENT_FETCHES = 6


# ============================================================
# SYMBOL FILTERS
# ============================================================

SYMBOL_BLOCKLIST: set[str] = {
    "BTCUPUSDT",
    "BTCDOWNUSDT",
    "ETHUPUSDT",
    "ETHDOWNUSDT",
    "BNBUPUSDT",
    "BNBDOWNUSDT",
    "USDCUSDT",
    "BUSDUSDT",
    "TUSDUSDT",
    "USDTUSDT",
    "DAIUSDT",
    "FRAXUSDT",
    "USTCUSDT",
}

SYMBOL_BLOCKLIST_SUFFIXES: tuple[str, ...] = (
    "UPUSDT",
    "DOWNUSDT",
    "BULLUSDT",
    "BEARUSDT",
)


# ============================================================
# RUNTIME STATE
# ============================================================

RECENTLY_SCANNED: set[str] = set()

ALERT_CACHE: dict[str, float] = {}

_SEM: asyncio.Semaphore | None = None

_shutdown = asyncio.Event()


# ============================================================
# SEMAPHORE
# ============================================================

def get_semaphore() -> asyncio.Semaphore:

    global _SEM

    if _SEM is None:
        _SEM = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    return _SEM


# ============================================================
# SHUTDOWN
# ============================================================

def _handle_signal(sig: int, _frame) -> None:

    log.warning(
        "Received signal %s — shutting down gracefully...",
        sig,
    )

    _shutdown.set()


# ============================================================
# DATAFRAME
# ============================================================

def build_dataframe(klines: list) -> pd.DataFrame:

    df = pd.DataFrame(
        klines,
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ],
    )

    for col in (
        "open",
        "high",
        "low",
        "close",
        "volume",
    ):
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce",
        )

    df["time"] = pd.to_datetime(
        df["time"],
        unit="ms",
        utc=True,
    )

    return df


# ============================================================
# ALERT CACHE
# ============================================================

def _prune_alert_cache() -> None:

    cutoff = time.time() - ALERT_COOLDOWN

    stale = [
        k
        for k, v in ALERT_CACHE.items()
        if v < cutoff
    ]

    for k in stale:
        del ALERT_CACHE[k]

    if stale:
        log.debug(
            "Pruned %d stale cooldown entries",
            len(stale),
        )


def is_on_cooldown(
    symbol: str,
    side: str,
) -> bool:

    key = f"{symbol}:{side}"

    return (
        time.time()
        - ALERT_CACHE.get(key, 0)
    ) < ALERT_COOLDOWN


def update_cooldown(
    symbol: str,
    side: str,
) -> None:

    ALERT_CACHE[f"{symbol}:{side}"] = time.time()


# ============================================================
# SYMBOL FILTER
# ============================================================

def is_tradeable(symbol: str) -> bool:

    if not symbol.isascii():
        return False

    if not symbol.endswith("USDT"):
        return False

    if symbol in SYMBOL_BLOCKLIST:
        return False

    if any(
        symbol.endswith(sfx)
        for sfx in SYMBOL_BLOCKLIST_SUFFIXES
    ):
        return False

    return True


# ============================================================
# SCAN SINGLE SYMBOL
# ============================================================

async def scan_symbol(
    client: httpx.AsyncClient,
    symbol: str,
    btc_15m: pd.DataFrame,
):

    async with get_semaphore():

        return await _scan_symbol_inner(
            client,
            symbol,
            btc_15m,
        )


async def _scan_symbol_inner(
    client: httpx.AsyncClient,
    symbol: str,
    btc_15m: pd.DataFrame,
):

    try:

        klines_15m, klines_1h, klines_4h = await asyncio.gather(
            fetch_klines(
                client,
                symbol,
                interval="15m",
                limit=300,
            ),
            fetch_klines(
                client,
                symbol,
                interval="1h",
                limit=300,
            ),
            fetch_klines(
                client,
                symbol,
                interval="4h",
                limit=300,
            ),
        )

        if (
            len(klines_15m) < 100
            or len(klines_1h) < 100
            or len(klines_4h) < 100
        ):
            return {
                "scanned": 0,
                "signals": 0,
                "errors": 0,
            }

        df_15m = build_dataframe(klines_15m)
        df_1h = build_dataframe(klines_1h)
        df_4h = build_dataframe(klines_4h)

        recent_volume = (
            df_15m["volume"]
            .iloc[-6:-1]
            .median()
        )

        if recent_volume <= 0:
            return {
                "scanned": 1,
                "signals": 0,
                "errors": 0,
            }

        signal_data = build_signal(
            symbol=symbol,
            df_15m=df_15m,
            df_1h=df_1h,
            df_4h=df_4h,
            btc_15m=btc_15m,
        )

        if not signal_data:
            return {
                "scanned": 1,
                "signals": 0,
                "errors": 0,
            }

        if is_on_cooldown(
            signal_data["symbol"],
            signal_data["side"],
        ):
            return {
                "scanned": 1,
                "signals": 0,
                "errors": 0,
            }

        update_cooldown(
            signal_data["symbol"],
            signal_data["side"],
        )

        log.info(
            "[SIGNAL] %s %s %s score=%s",
            signal_data["symbol"],
            signal_data["side"],
            signal_data["grade"],
            signal_data["score"],
        )

        loop = asyncio.get_running_loop()

        await loop.run_in_executor(
            None,
            save_signal,
            signal_data,
        )

        r = await client.post(
            API_URL,
            json=signal_data,
            timeout=20,
        )

        if r.status_code not in (200, 201):

            log.warning(
                "[POST ERROR] %s — HTTP %s: %s",
                symbol,
                r.status_code,
                r.text,
            )

        return {
            "scanned": 1,
            "signals": 1,
            "errors": 0,
        }

    except Exception:

        log.exception(
            "[SCAN ERROR] %s",
            symbol,
        )

        return {
            "scanned": 1,
            "signals": 0,
            "errors": 1,
        }


# ============================================================
# SCAN MARKET
# ============================================================

async def scan_market(
    client: httpx.AsyncClient,
) -> None:

    global RECENTLY_SCANNED

    raw_symbols = await fetch_usdt_perp_symbols()

    if not raw_symbols:

        log.error(
            "No symbols loaded — aborting cycle",
        )

        return

    symbols = [
        s
        for s in raw_symbols
        if is_tradeable(s)
    ]

    available = [
        s
        for s in symbols
        if s not in RECENTLY_SCANNED
    ]

    if len(available) < SCAN_SYMBOLS_PER_CYCLE:

        log.info(
            "Rotation pool exhausted — resetting",
        )

        RECENTLY_SCANNED = set()

        available = symbols.copy()

    random.shuffle(available)

    batch_symbols = available[:SCAN_SYMBOLS_PER_CYCLE]

    for s in batch_symbols:
        RECENTLY_SCANNED.add(s)

    log.info(
        "[%s] scanning %d symbols (%d in rotation pool, %d total filtered)...",
        datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
        len(batch_symbols),
        len(available),
        len(symbols),
    )

    try:

        btc_15m_raw = await fetch_klines(
            client,
            "BTCUSDT",
            interval="15m",
            limit=300,
        )

    except Exception:

        log.exception(
            "[ABORT] BTC klines fetch raised — skipping cycle",
        )

        return

    if len(btc_15m_raw) < 100:

        log.error(
            "[ABORT] BTC klines too short (%d rows) — skipping cycle",
            len(btc_15m_raw),
        )

        return

    btc_15m = build_dataframe(
        btc_15m_raw,
    )

    _prune_alert_cache()

    scanned_count = 0
    signal_count = 0
    error_count = 0

    for i in range(
        0,
        len(batch_symbols),
        BATCH_SIZE,
    ):

        if _shutdown.is_set():

            log.info(
                "Shutdown requested — stopping mid-cycle",
            )

            return

        batch = batch_symbols[
            i:i + BATCH_SIZE
        ]

        results = await asyncio.gather(
            *[
                scan_symbol(
                    client,
                    sym,
                    btc_15m,
                )
                for sym in batch
            ]
        )

        for r in results:

            if not r:
                continue

            scanned_count += r.get(
                "scanned",
                0,
            )

            signal_count += r.get(
                "signals",
                0,
            )

            error_count += r.get(
                "errors",
                0,
            )

        await asyncio.sleep(
            BATCH_SLEEP,
        )

    log.info(
        "Cycle complete | scanned=%d | signals=%d | errors=%d",
        scanned_count,
        signal_count,
        error_count,
    )


# ============================================================
# MAIN LOOP
# ============================================================

async def main() -> None:

    loop = asyncio.get_running_loop()

    for sig in (
        signal.SIGINT,
        signal.SIGTERM,
    ):
        loop.add_signal_handler(
            sig,
            _handle_signal,
            sig,
            None,
        )

    log.info(
        "Scanner starting — interval=%ds, batch=%d, concurrency=%d",
        SCAN_INTERVAL,
        BATCH_SIZE,
        MAX_CONCURRENT_FETCHES,
    )

    async with httpx.AsyncClient() as client:

        while not _shutdown.is_set():

            next_run = (
                time.monotonic()
                + SCAN_INTERVAL
            )

            try:

                log.info(
                    "Scanner tick...",
                )

                await scan_market(
                    client,
                )

            except Exception:

                log.exception(
                    "Unhandled error in scan_market",
                )

            sleep_for = max(
                0.0,
                next_run - time.monotonic(),
            )

            if (
                sleep_for > 0
                and not _shutdown.is_set()
            ):

                log.info(
                    "Next scan in %.1fs...",
                    sleep_for,
                )

                try:

                    await asyncio.wait_for(
                        asyncio.shield(
                            _shutdown.wait(),
                        ),
                        timeout=sleep_for,
                    )

                except asyncio.TimeoutError:
                    pass

    log.info(
        "Scanner shut down cleanly.",
    )


if __name__ == "__main__":
    asyncio.run(main())