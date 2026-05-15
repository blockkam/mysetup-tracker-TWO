from __future__ import annotations

import pandas as pd


PIVOT_LENGTH = 5


# ============================================================
# SWING HIGH
# ============================================================

def is_swing_high(
    df: pd.DataFrame,
    idx: int,
    length: int = PIVOT_LENGTH,
):

    if idx < length or idx >= len(df) - length:
        return False

    high = df["high"].iloc[idx]

    left = df["high"].iloc[idx - length:idx]
    right = df["high"].iloc[idx + 1:idx + length + 1]

    return high > left.max() and high > right.max()


# ============================================================
# SWING LOW
# ============================================================

def is_swing_low(
    df: pd.DataFrame,
    idx: int,
    length: int = PIVOT_LENGTH,
):

    if idx < length or idx >= len(df) - length:
        return False

    low = df["low"].iloc[idx]

    left = df["low"].iloc[idx - length:idx]
    right = df["low"].iloc[idx + 1:idx + length + 1]

    return low < left.min() and low < right.min()


# ============================================================
# FIND RECENT SWINGS
# ============================================================

def find_recent_swings(
    df: pd.DataFrame,
    length: int = PIVOT_LENGTH,
):

    swing_highs = []
    swing_lows = []

    start = max(length, len(df) - 50)

    for i in range(start, len(df) - length):

        if is_swing_high(df, i, length):

            swing_highs.append({
                "index": i,
                "price": df["high"].iloc[i],
            })

        if is_swing_low(df, i, length):

            swing_lows.append({
                "index": i,
                "price": df["low"].iloc[i],
            })

    return swing_highs, swing_lows


# ============================================================
# DETECT STRUCTURE
# ============================================================

def detect_structure(df: pd.DataFrame):

    result = {
        "bullish_bos": False,
        "bearish_bos": False,
        "bullish_choch": False,
        "bearish_choch": False,
        "trend": "neutral",
        "swing_high": None,
        "swing_low": None,
    }

    swing_highs, swing_lows = find_recent_swings(df)

    if not swing_highs or not swing_lows:
        return result

    last_swing_high = swing_highs[-1]
    last_swing_low = swing_lows[-1]

    result["swing_high"] = last_swing_high["price"]
    result["swing_low"] = last_swing_low["price"]

    last_close = df["close"].iloc[-1]

    # ========================================================
    # BOS
    # ========================================================

    if last_close > last_swing_high["price"]:

        result["bullish_bos"] = True
        result["trend"] = "bullish"

    if last_close < last_swing_low["price"]:

        result["bearish_bos"] = True
        result["trend"] = "bearish"

    # ========================================================
    # CHOCH
    # ========================================================

    if (
        result["bullish_bos"]
        and last_swing_low["index"] > last_swing_high["index"]
    ):

        result["bullish_choch"] = True

    if (
        result["bearish_bos"]
        and last_swing_high["index"] > last_swing_low["index"]
    ):

        result["bearish_choch"] = True

    return result