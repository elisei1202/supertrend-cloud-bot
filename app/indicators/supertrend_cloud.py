import pandas as pd
import numpy as np
from typing import Tuple, Literal


def calculate_supertrend(df: pd.DataFrame, period: int, multiplier: float) -> pd.Series:
    """
    Calculează SuperTrend indicator exact ca în TradingView
    
    Formula:
    - hl2 = (high + low) / 2
    - atr = RMA (Wilder's smoothing) al True Range cu perioada specificată
    - basicUpperBand = hl2 + (multiplier × atr)
    - basicLowerBand = hl2 - (multiplier × atr)
    
    Direction logic:
    - Dacă era bearish și close > upper_band anterior → flip to bullish
    - Dacă era bullish și close < lower_band anterior → flip to bearish
    """
    n = len(df)
    
    # Calculate HL2
    hl2 = (df['high'] + df['low']) / 2
    
    # Calculate True Range
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift(1))
    low_close = np.abs(df['low'] - df['close'].shift(1))
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    # RMA (Running Moving Average / Wilder's smoothing) - ca în TradingView
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    # Calculate basic bands
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    # Initialize arrays
    upper_band = np.zeros(n)
    lower_band = np.zeros(n)
    supertrend = np.zeros(n)
    direction = np.zeros(n)  # 1 = uptrend (bullish), -1 = downtrend (bearish)
    
    # First value initialization - handle potential NaN
    first_valid_idx = 0
    for i in range(n):
        if not pd.isna(basic_upper.iloc[i]) and not pd.isna(basic_lower.iloc[i]):
            first_valid_idx = i
            break
    
    upper_band[first_valid_idx] = basic_upper.iloc[first_valid_idx]
    lower_band[first_valid_idx] = basic_lower.iloc[first_valid_idx]
    direction[first_valid_idx] = 1  # Start with uptrend assumption
    supertrend[first_valid_idx] = lower_band[first_valid_idx]
    
    # Copy initial values to earlier indices if any
    for i in range(first_valid_idx):
        upper_band[i] = upper_band[first_valid_idx]
        lower_band[i] = lower_band[first_valid_idx]
        direction[i] = 1
        supertrend[i] = lower_band[first_valid_idx]
    
    for i in range(first_valid_idx + 1, n):
        # Handle NaN values
        if pd.isna(basic_upper.iloc[i]) or pd.isna(basic_lower.iloc[i]):
            upper_band[i] = upper_band[i-1]
            lower_band[i] = lower_band[i-1]
            direction[i] = direction[i-1]
            supertrend[i] = supertrend[i-1]
            continue
        
        # Upper Band calculation (TradingView logic)
        if basic_upper.iloc[i] < upper_band[i-1] or df['close'].iloc[i-1] > upper_band[i-1]:
            upper_band[i] = basic_upper.iloc[i]
        else:
            upper_band[i] = upper_band[i-1]
        
        # Lower Band calculation (TradingView logic)
        if basic_lower.iloc[i] > lower_band[i-1] or df['close'].iloc[i-1] < lower_band[i-1]:
            lower_band[i] = basic_lower.iloc[i]
        else:
            lower_band[i] = lower_band[i-1]
        
        # Direction calculation (TradingView logic)
        if direction[i-1] == -1:  # Was bearish (supertrend was at upper band)
            if df['close'].iloc[i] > upper_band[i-1]:  # Close crosses above upper band
                direction[i] = 1  # Flip to bullish
            else:
                direction[i] = -1  # Stay bearish
        else:  # Was bullish (supertrend was at lower band)
            if df['close'].iloc[i] < lower_band[i-1]:  # Close crosses below lower band
                direction[i] = -1  # Flip to bearish
            else:
                direction[i] = 1  # Stay bullish
        
        # SuperTrend value - follows the appropriate band based on direction
        supertrend[i] = lower_band[i] if direction[i] == 1 else upper_band[i]
    
    return pd.Series(supertrend, index=df.index)


def calculate_supertrend_cloud(
    df: pd.DataFrame,
    st1_period: int,
    st1_multiplier: float,
    st2_period: int,
    st2_multiplier: float
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculează SuperTrend Cloud cu două SuperTrend-uri
    
    Returns:
        (upper_cloud, lower_cloud, zone)
    """
    # Calculate two SuperTrend indicators
    st1 = calculate_supertrend(df, st1_period, st1_multiplier)
    st2 = calculate_supertrend(df, st2_period, st2_multiplier)
    
    # Cloud boundaries
    upper_cloud = pd.Series([max(st1.iloc[i], st2.iloc[i]) for i in range(len(df))], index=df.index)
    lower_cloud = pd.Series([min(st1.iloc[i], st2.iloc[i]) for i in range(len(df))], index=df.index)
    
    return upper_cloud, lower_cloud


def get_zone(close: float, upper_cloud: float, lower_cloud: float) -> Literal["OVER", "UNDER", "IN"]:
    """
    Determină zona curentă bazat pe close price și cloud boundaries
    
    - OVER: close > upper_cloud (peste cloud)
    - UNDER: close < lower_cloud (sub cloud)
    - IN: lower_cloud <= close <= upper_cloud (în cloud)
    """
    if close > upper_cloud:
        return "OVER"
    elif close < lower_cloud:
        return "UNDER"
    else:
        return "IN"
