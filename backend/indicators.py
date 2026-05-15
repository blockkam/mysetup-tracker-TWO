from __future__ import annotations

import pandas as pd


# =========================================================
# EMA
# =========================================================

def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


# =========================================================
# ATR
# =========================================================

def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:

    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()

    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)

    return true_range.rolling(length).mean()


# =========================================================
# LIQUIDITY SWEEPS
# =========================================================

def bullish_sweep(df: pd.DataFrame, lookback: int = 10) -> bool:

    if len(df) < lookback + 2:
        return False

    prev_low = df['low'].iloc[-lookback:-1].min()

    current_low = df.iloc[-1]['low']
    current_close = df.iloc[-1]['close']

    return current_low < prev_low and current_close > prev_low


def bearish_sweep(df: pd.DataFrame, lookback: int = 10) -> bool:

    if len(df) < lookback + 2:
        return False

    prev_high = df['high'].iloc[-lookback:-1].max()

    current_high = df.iloc[-1]['high']
    current_close = df.iloc[-1]['close']

    return current_high > prev_high and current_close < prev_high


# =========================================================
# DISPLACEMENT
# =========================================================

def bullish_displacement(df: pd.DataFrame) -> bool:

    if len(df) < 20:
        return False

    body = abs(df.iloc[-1]['close'] - df.iloc[-1]['open'])
    avg_body = (df['close'] - df['open']).abs().rolling(20).mean().iloc[-1]

    return body > avg_body * 1.5 and df.iloc[-1]['close'] > df.iloc[-1]['open']


def bearish_displacement(df: pd.DataFrame) -> bool:

    if len(df) < 20:
        return False

    body = abs(df.iloc[-1]['close'] - df.iloc[-1]['open'])
    avg_body = (df['close'] - df['open']).abs().rolling(20).mean().iloc[-1]

    return body > avg_body * 1.5 and df.iloc[-1]['close'] < df.iloc[-1]['open']


# =========================================================
# FVG
# =========================================================

def detect_bullish_fvg(df: pd.DataFrame):

    out = []

    for i in range(2, len(df)):

        c1_high = df.iloc[i - 2]['high']
        c3_low = df.iloc[i]['low']

        if c3_low > c1_high:

            out.append({
                'index': i,
                'top': c3_low,
                'bottom': c1_high,
            })

    return out


def detect_bearish_fvg(df: pd.DataFrame):

    out = []

    for i in range(2, len(df)):

        c1_low = df.iloc[i - 2]['low']
        c3_high = df.iloc[i]['high']

        if c3_high < c1_low:

            out.append({
                'index': i,
                'top': c1_low,
                'bottom': c3_high,
            })

    return out


# =========================================================
# VOLUME EXPANSION
# =========================================================

def volume_expansion(df: pd.DataFrame) -> bool:

    if len(df) < 20:
        return False

    avg = df['volume'].rolling(20).mean().iloc[-1]

    return df.iloc[-1]['volume'] > avg * 1.2


# =========================================================
# HTF BIAS
# =========================================================

def htf_bias(df: pd.DataFrame):

    df = df.copy()

    df['ema_50'] = ema(df['close'], 50)
    df['ema_200'] = ema(df['close'], 200)

    last = df.iloc[-1]

    if last['close'] > last['ema_50'] > last['ema_200']:
        return 'bull'

    if last['close'] < last['ema_50'] < last['ema_200']:
        return 'bear'

    return 'neutral'