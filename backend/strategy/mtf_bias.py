from __future__ import annotations

import pandas as pd


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def get_mtf_bias(
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
):

    result = {
        "bullish": False,
        "bearish": False,
        "score": 0,
        "reasons": [],
    }

    # =========================================================
    # 4H BIAS
    # =========================================================

    close_4h = df_4h["close"]
    ema50_4h = ema(close_4h, 50)
    ema100_4h = ema(close_4h, 100)

    last_4h = close_4h.iloc[-1]

    cond_4h = 0

    if last_4h > ema50_4h.iloc[-1]:
        cond_4h += 1

    if last_4h > ema100_4h.iloc[-1]:
        cond_4h += 1

    if ema50_4h.iloc[-1] > ema50_4h.iloc[-5]:
        cond_4h += 1

    # =========================================================
    # 1H TREND
    # =========================================================

    close_1h = df_1h["close"]

    ema20_1h = ema(close_1h, 20)
    ema50_1h = ema(close_1h, 50)

    bullish_1h = (
        close_1h.iloc[-1] > ema20_1h.iloc[-1]
        and ema20_1h.iloc[-1] > ema50_1h.iloc[-1]
    )

    bearish_1h = (
        close_1h.iloc[-1] < ema20_1h.iloc[-1]
        and ema20_1h.iloc[-1] < ema50_1h.iloc[-1]
    )

    # =========================================================
    # 15M MOMENTUM
    # =========================================================

    close_15m = df_15m["close"]

    ema20_15m = ema(close_15m, 20)

    bullish_15m = close_15m.iloc[-1] > ema20_15m.iloc[-1]
    bearish_15m = close_15m.iloc[-1] < ema20_15m.iloc[-1]

    # =========================================================
    # FINAL BIAS
    # =========================================================

    if bullish_1h and bullish_15m:

        result["bullish"] = True
        result["score"] += 2

        result["reasons"].append("1H bullish")
        result["reasons"].append("15m bullish")

    if bearish_1h and bearish_15m:

        result["bearish"] = True
        result["score"] += 2

        result["reasons"].append("1H bearish")
        result["reasons"].append("15m bearish")

    # 4H supportive only

    if cond_4h >= 2:

        result["score"] += 1
        result["reasons"].append("4H supportive")

    return result