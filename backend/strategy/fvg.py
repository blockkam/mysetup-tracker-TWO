from __future__ import annotations

import pandas as pd


# ============================================================
# DETECT BULLISH FVG
# ============================================================

def detect_bullish_fvg(df: pd.DataFrame):

    if len(df) < 5:
        return None

    for i in range(len(df) - 3, 1, -1):

        high_2 = df["high"].iloc[i - 2]
        low_now = df["low"].iloc[i]

        # bullish gap
        if low_now > high_2:

            gap_top = low_now
            gap_bottom = high_2

            midpoint = (
                gap_top + gap_bottom
            ) / 2

            return {
                "valid": True,
                "top": gap_top,
                "bottom": gap_bottom,
                "mid": midpoint,
                "index": i,
            }

    return None


# ============================================================
# DETECT BEARISH FVG
# ============================================================

def detect_bearish_fvg(df: pd.DataFrame):

    if len(df) < 5:
        return None

    for i in range(len(df) - 3, 1, -1):

        low_2 = df["low"].iloc[i - 2]
        high_now = df["high"].iloc[i]

        # bearish gap
        if high_now < low_2:

            gap_top = low_2
            gap_bottom = high_now

            midpoint = (
                gap_top + gap_bottom
            ) / 2

            return {
                "valid": True,
                "top": gap_top,
                "bottom": gap_bottom,
                "mid": midpoint,
                "index": i,
            }

    return None


# ============================================================
# BULLISH RECLAIM
# ============================================================

def bullish_fvg_reclaim(df: pd.DataFrame):

    fvg = detect_bullish_fvg(df)

    if not fvg:
        return False

    last_close = df["close"].iloc[-1]

    return last_close > fvg["mid"]


# ============================================================
# BEARISH RECLAIM
# ============================================================

def bearish_fvg_reclaim(df: pd.DataFrame):

    fvg = detect_bearish_fvg(df)

    if not fvg:
        return False

    last_close = df["close"].iloc[-1]

    return last_close < fvg["mid"]