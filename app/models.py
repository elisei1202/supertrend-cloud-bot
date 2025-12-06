from dataclasses import dataclass, field
from typing import Literal, Optional
from datetime import datetime


@dataclass
class PositionState:
    """State pentru o poziție per simbol"""
    symbol: str
    pos_state: Literal["FLAT", "LONG", "SHORT"] = "FLAT"
    prev_zone: Literal["OVER", "UNDER", "IN", "NONE"] = "NONE"
    current_zone: Literal["OVER", "UNDER", "IN", "NONE"] = "NONE"
    qty: float = 0.0
    entry_price: float = 0.0
    unrealized_pnl: float = 0.0
    last_signal: str = "N/A"
    last_candle_time: int = 0
    last_update: datetime = field(default_factory=datetime.now)


@dataclass
class TradingState:
    """State global de trading"""
    trading_enabled: bool = False
    connection_ok: bool = False
    positions: dict[str, PositionState] = field(default_factory=dict)
    
    def get_position(self, symbol: str) -> PositionState:
        if symbol not in self.positions:
            self.positions[symbol] = PositionState(symbol=symbol)
        return self.positions[symbol]


# Global state instance
trading_state = TradingState()
