from __future__ import annotations

import httpx


BINANCE_BASE = "https://fapi.binance.com"


# ============================================================
# FETCH ALL USDT PERP SYMBOLS
# ============================================================

async def fetch_usdt_perp_symbols():

    url = f"{BINANCE_BASE}/fapi/v1/exchangeInfo"

    try:

        async with httpx.AsyncClient() as client:

            r = await client.get(
                url,
                timeout=20
            )

            if r.status_code != 200:

                print(f"exchangeInfo failed: {r.status_code}")

                return []

            data = r.json()

            symbols = []

            for item in data.get("symbols", []):

                if (
                    item.get("contractType") == "PERPETUAL"
                    and item.get("quoteAsset") == "USDT"
                    and item.get("status") == "TRADING"
                ):

                    symbols.append(item["symbol"])

            print(f"Loaded {len(symbols)} Binance perp symbols")

            return sorted(symbols)

    except Exception as e:

        print("symbol fetch error:", e)

        return []


# ============================================================
# FETCH KLINES
# ============================================================

async def fetch_klines(
    client: httpx.AsyncClient,
    symbol: str,
    interval: str = "15m",
    start_ms: int | None = None,
    limit: int = 200,
):

    url = f"{BINANCE_BASE}/fapi/v1/klines"

    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }

    if start_ms:
        params["startTime"] = start_ms

    try:

        r = await client.get(
            url,
            params=params,
            timeout=20
        )

        if r.status_code != 200:

            print(
                f"kline error {symbol}: "
                f"{r.status_code}"
            )

            return []

        rows = r.json()

        out = []

        for row in rows:

            out.append([
                int(row[0]),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                float(row[5]),
            ])

        return out

    except Exception as e:

        print(f"kline fetch failed {symbol}: {e}")

        return []