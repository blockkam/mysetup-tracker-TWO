from __future__ import annotations

import pandas as pd


def ema(series, length):

    return series.ewm(
        span=length,
        adjust=False
    ).mean()


# ============================================================
# BTC MARKET FILTER
# ============================================================

def get_btc_bias(df: pd.DataFrame):

    result = {
        "bullish": False,
        "bearish": False,
        "strong_trend": False,
        "score": 0,
    }

    if len(df) < 100:
        return result

    close = df["close"]

    ema20 = ema(close, 20)
    ema50 = ema(close, 50)

    last_close = close.iloc[-1]

    # ========================================================
    # BULLISH
    # ========================================================

    if (
        last_close > ema20.iloc[-1]
        and ema20.iloc[-1] > ema50.iloc[-1]
    ):

        result["bullish"] = True
        result["score"] += 1

    # ========================================================
    # BEARISH
    # ========================================================

    if (
        last_close < ema20.iloc[-1]
        and ema20.iloc[-1] < ema50.iloc[-1]
    ):

        result["bearish"] = True
        result["score"] += 1

    # ========================================================
    # STRONG TREND
    # ========================================================

    ema_distance = abs(
        ema20.iloc[-1] - ema50.iloc[-1]
    ) / ema50.iloc[-1]

    if ema_distance > 0.01:

        result["strong_trend"] = True
        result["score"] += 1

    return result