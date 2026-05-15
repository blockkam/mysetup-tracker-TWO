from __future__ import annotations

import asyncio

import httpx

from tracking.tracker import (
    fetch_open_trades,
    close_trade,
)

from binance_client import fetch_klines


# ============================================================
# CHECK SINGLE TRADE
# ============================================================

async def check_trade(
    client: httpx.AsyncClient,
    trade: dict,
):

    symbol = trade["symbol"]

    try:

        klines = await fetch_klines(
            client,
            symbol,
            interval="5m",
            limit=2,
        )

        if not klines:
            return

        latest = klines[-1]

        high = float(latest[2])

        low = float(latest[3])

        side = trade["side"]

        entry = float(trade["entry"])

        sl = float(trade["sl"])

        tp1 = float(trade["tp1"])

        # ====================================================
        # LONG
        # ====================================================

        if side == "LONG":

            # SL hit
            if low <= sl:

                pnl = -1.0

                close_trade(
                    trade["id"],
                    "LOSS",
                    pnl,
                )

                print(
                    f"[LOSS] "
                    f"{symbol}"
                )

                return

            # TP hit
            if high >= tp1:

                pnl = trade["rr1"]

                close_trade(
                    trade["id"],
                    "WIN",
                    pnl,
                )

                print(
                    f"[WIN] "
                    f"{symbol}"
                )

                return

        # ====================================================
        # SHORT
        # ====================================================

        if side == "SHORT":

            # SL hit
            if high >= sl:

                pnl = -1.0

                close_trade(
                    trade["id"],
                    "LOSS",
                    pnl,
                )

                print(
                    f"[LOSS] "
                    f"{symbol}"
                )

                return

            # TP hit
            if low <= tp1:

                pnl = trade["rr1"]

                close_trade(
                    trade["id"],
                    "WIN",
                    pnl,
                )

                print(
                    f"[WIN] "
                    f"{symbol}"
                )

                return

    except Exception as e:

        print(
            f"[MONITOR ERROR] "
            f"{symbol}: {e}"
        )


# ============================================================
# MONITOR LOOP
# ============================================================

async def monitor_loop():

    while True:

        try:

            trades = fetch_open_trades()

            if trades:

                print(
                    f"monitoring "
                    f"{len(trades)} open trades..."
                )

                async with httpx.AsyncClient() as client:

                    tasks = []

                    for trade in trades:

                        tasks.append(
                            check_trade(
                                client,
                                trade,
                            )
                        )

                    await asyncio.gather(*tasks)

            else:

                print(
                    "no open trades"
                )

        except Exception as e:

            print(
                f"[MONITOR ERROR] {e}"
            )

        await asyncio.sleep(60)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        monitor_loop()
    )