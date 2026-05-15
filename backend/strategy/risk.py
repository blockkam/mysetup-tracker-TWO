from __future__ import annotations

import pandas as pd

from indicators import atr


# ============================================================
# BUILD RISK MODEL
# ============================================================

def build_risk_model(
    side: str,
    df_15m: pd.DataFrame,
):

    last = df_15m.iloc[-1]

    entry = float(last["close"])

    atr_val = atr(df_15m).iloc[-1]

    # ========================================================
    # LONG
    # ========================================================

    if side == "LONG":

        recent_low = df_15m["low"].tail(20).min()

        sl = recent_low - atr_val * 0.3

        risk = entry - sl

        tp1 = entry + risk * 1.5
        tp2 = entry + risk * 3.0
        tp3 = entry + risk * 5.0

    # ========================================================
    # SHORT
    # ========================================================

    else:

        recent_high = df_15m["high"].tail(20).max()

        sl = recent_high + atr_val * 0.3

        risk = sl - entry

        tp1 = entry - risk * 1.5
        tp2 = entry - risk * 3.0
        tp3 = entry - risk * 5.0

    if risk <= 0:
        return None

    rr1 = abs(tp1 - entry) / risk
    rr2 = abs(tp2 - entry) / risk
    rr3 = abs(tp3 - entry) / risk

    if rr1 < 1.5:
        return None

    return {
        "entry": round(entry, 6),
        "sl": round(sl, 6),
        "tp1": round(tp1, 6),
        "tp2": round(tp2, 6),
        "tp3": round(tp3, 6),
        "rr1": round(rr1, 2),
        "rr2": round(rr2, 2),
        "rr3": round(rr3, 2),
    }