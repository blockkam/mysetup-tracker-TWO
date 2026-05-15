from __future__ import annotations

import pandas as pd


# ============================================================
# BULLISH EXECUTION
# ============================================================

def bullish_execution(df: pd.DataFrame):

    if len(df) < 5:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # bullish candle
    bullish_close = (
        last["close"] > last["open"]
    )

    # continuation strength
    continuation = (
        last["close"] > prev["close"]
    )

    # higher low
    higher_low = (
        last["low"] >= prev["low"]
    )

    return (
        bullish_close
        and continuation
        and higher_low
    )


# ============================================================
# BEARISH EXECUTION
# ============================================================

def bearish_execution(df: pd.DataFrame):

    if len(df) < 5:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]

    # bearish candle
    bearish_close = (
        last["close"] < last["open"]
    )

    # continuation weakness
    continuation = (
        last["close"] < prev["close"]
    )

    # lower high
    lower_high = (
        last["high"] <= prev["high"]
    )

    return (
        bearish_close
        and continuation
        and lower_high
    )