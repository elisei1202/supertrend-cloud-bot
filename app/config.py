import os
from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Bybit API
    BYBIT_API_KEY: str = ""
    BYBIT_API_SECRET: str = ""
    BYBIT_BASE_URL: str = "https://api.bybit.com"
    
    # Trading Config
    SYMBOLS: str = "BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT"
    POSITION_SIZE_USDT: float = 100
    LEVERAGE: int = 20
    TIMEFRAME: str = "15"  # 15m in minutes
    CANDLES_LIMIT: int = 400
    
    # SuperTrend Parameters
    ST1_PERIOD: int = 10
    ST1_MULTIPLIER: float = 3.0
    ST2_PERIOD: int = 10
    ST2_MULTIPLIER: float = 6.0
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = int(os.getenv("PORT", "8000"))
    
    class Config:
        env_file = ".env"
        case_sensitive = True
    
    @property
    def symbol_list(self) -> List[str]:
        return [s.strip() for s in self.SYMBOLS.split(",") if s.strip()]
    
    @property
    def timeframe_display(self) -> str:
        """Convert timeframe minutes to human-readable format (15m, 1h, 4h, etc.)"""
        minutes = int(self.TIMEFRAME)
        if minutes < 60:
            return f"{minutes}m"
        elif minutes == 60:
            return "1h"
        else:
            hours = minutes // 60
            return f"{hours}h"


settings = Settings()
