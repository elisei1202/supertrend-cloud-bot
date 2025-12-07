import aiohttp
import asyncio
import time
import hmac
import hashlib
import json
from typing import Optional, Dict, Any, List
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class BybitClient:
    """Async Bybit V5 API Client pentru Unified Trading"""
    
    def __init__(self):
        self.base_url = settings.BYBIT_BASE_URL
        self.api_key = settings.BYBIT_API_KEY
        self.api_secret = settings.BYBIT_API_SECRET
        self.recv_window = 5000
        
    def _generate_signature(self, timestamp: str, params: str) -> str:
        """Generează HMAC SHA256 signature pentru autentificare"""
        param_str = f"{timestamp}{self.api_key}{self.recv_window}{params}"
        return hmac.new(
            self.api_secret.encode('utf-8'),
            param_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False
    ) -> Dict[str, Any]:
        """Generic async request method cu proper error handling"""
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json"
        }
        
        # Prepare params
        if params is None:
            params = {}
        
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        
        if signed:
            timestamp = str(int(time.time() * 1000))
            
            if method == "GET":
                query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
                signature = self._generate_signature(timestamp, query_string)
                headers.update({
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": str(self.recv_window)
                })
            else:  # POST
                param_str = json.dumps(params) if params else ""
                signature = self._generate_signature(timestamp, param_str)
                headers.update({
                    "X-BAPI-API-KEY": self.api_key,
                    "X-BAPI-TIMESTAMP": timestamp,
                    "X-BAPI-SIGN": signature,
                    "X-BAPI-RECV-WINDOW": str(self.recv_window)
                })
        
        try:
            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    async with session.get(url, headers=headers, params=params) as resp:
                        # Check HTTP status first
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f"HTTP {resp.status} error for {endpoint}: {error_text}")
                            return {"retCode": -1, "retMsg": f"HTTP {resp.status}: {error_text}"}
                        
                        try:
                            data = await resp.json()
                        except aiohttp.ContentTypeError as e:
                            logger.error(f"Invalid JSON response for {endpoint}: {e}")
                            return {"retCode": -1, "retMsg": f"Invalid JSON response: {e}"}
                        
                        return data
                else:  # POST
                    async with session.post(url, headers=headers, json=params) as resp:
                        # Check HTTP status first
                        if resp.status != 200:
                            error_text = await resp.text()
                            logger.error(f"HTTP {resp.status} error for {endpoint}: {error_text}")
                            return {"retCode": -1, "retMsg": f"HTTP {resp.status}: {error_text}"}
                        
                        try:
                            data = await resp.json()
                        except aiohttp.ContentTypeError as e:
                            logger.error(f"Invalid JSON response for {endpoint}: {e}")
                            return {"retCode": -1, "retMsg": f"Invalid JSON response: {e}"}
                        
                        return data
                        
        except aiohttp.ClientConnectorError as e:
            logger.error(f"Connection error for {endpoint}: {e}")
            return {"retCode": -1, "retMsg": f"Connection error: {e}"}
        except asyncio.TimeoutError:
            logger.error(f"Timeout error for {endpoint}")
            return {"retCode": -1, "retMsg": "Request timeout"}
        except Exception as e:
            logger.error(f"Unexpected request error for {endpoint}: {type(e).__name__}: {e}")
            return {"retCode": -1, "retMsg": str(e)}
    
    async def get_klines(
        self,
        symbol: str,
        interval: str = "30",
        limit: int = 400
    ) -> List[List]:
        """
        Obține klines (OHLCV) pentru un simbol
        
        Returns:
            List of [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        """
        endpoint = "/v5/market/kline"
        params = {
            "category": "linear",
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        
        result = await self._request("GET", endpoint, params)
        
        if result.get("retCode") == 0:
            klines = result.get("result", {}).get("list", [])
            logger.debug(f"[{symbol}] Received {len(klines)} klines")
            return klines
        else:
            logger.error(f"[{symbol}] Get klines error: {result.get('retMsg')}")
            return []
    
    async def get_instruments_info(self, symbol: str) -> Dict[str, Any]:
        """Obține informații despre instrument (stepSize, minQty, etc.)"""
        endpoint = "/v5/market/instruments-info"
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        result = await self._request("GET", endpoint, params)
        
        if result.get("retCode") == 0:
            instruments = result.get("result", {}).get("list", [])
            if instruments:
                logger.debug(f"[{symbol}] Instrument info retrieved successfully")
                return instruments[0]
            else:
                logger.warning(f"[{symbol}] No instrument info found in response")
        else:
            logger.error(f"[{symbol}] Get instruments info error: {result.get('retMsg')}")
        
        return {}
    
    async def get_positions(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obține poziții active"""
        endpoint = "/v5/position/list"
        params = {
            "category": "linear",
            "settleCoin": "USDT"
        }
        
        if symbol:
            params["symbol"] = symbol
        
        result = await self._request("GET", endpoint, params, signed=True)
        
        if result.get("retCode") == 0:
            positions = result.get("result", {}).get("list", [])
            logger.debug(f"Retrieved {len(positions)} positions")
            return positions
        else:
            logger.error(f"Get positions error: {result.get('retMsg')}")
            return []
    
    async def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Setează leverage pentru un simbol (ISOLATED mode)"""
        endpoint = "/v5/position/set-leverage"
        params = {
            "category": "linear",
            "symbol": symbol,
            "buyLeverage": str(leverage),
            "sellLeverage": str(leverage)
        }
        
        result = await self._request("POST", endpoint, params, signed=True)
        
        # 110043 = leverage not modified (already at this level)
        if result.get("retCode") == 0 or result.get("retCode") == 110043:
            if result.get("retCode") == 110043:
                logger.debug(f"[{symbol}] Leverage already set to {leverage}x")
            else:
                logger.info(f"[{symbol}] Leverage set to {leverage}x")
            return True
        else:
            logger.error(f"[{symbol}] Set leverage error: {result.get('retMsg')}")
            return False
    
    async def switch_margin_mode(self, symbol: str, mode: str = "ISOLATED_MARGIN") -> bool:
        """Setează margin mode pentru un simbol"""
        endpoint = "/v5/position/switch-isolated"
        params = {
            "category": "linear",
            "symbol": symbol,
            "tradeMode": 1 if mode == "ISOLATED_MARGIN" else 0,  # 0=cross, 1=isolated
            "buyLeverage": str(settings.LEVERAGE),
            "sellLeverage": str(settings.LEVERAGE)
        }
        
        result = await self._request("POST", endpoint, params, signed=True)
        
        # 110043 = already in this mode
        if result.get("retCode") == 0 or result.get("retCode") == 110043:
            if result.get("retCode") == 110043:
                logger.debug(f"[{symbol}] Already in {mode} mode")
            else:
                logger.info(f"[{symbol}] Margin mode set to {mode}")
            return True
        else:
            logger.error(f"[{symbol}] Switch margin mode error: {result.get('retMsg')}")
            return False
    
    async def place_market_order(
        self,
        symbol: str,
        side: str,  # "Buy" or "Sell"
        qty: float,
        reduce_only: bool = False
    ) -> Optional[str]:
        """
        Plasează o ordine MARKET
        
        Returns:
            orderId dacă success, None dacă fail
        """
        endpoint = "/v5/order/create"
        params = {
            "category": "linear",
            "symbol": symbol,
            "side": side,
            "orderType": "Market",
            "qty": str(qty),
            "timeInForce": "IOC",  # Immediate or Cancel
            "reduceOnly": reduce_only
        }
        
        result = await self._request("POST", endpoint, params, signed=True)
        
        if result.get("retCode") == 0:
            order_id = result.get("result", {}).get("orderId")
            logger.info(f"[{symbol}] Market order placed: {side} {qty} | OrderID: {order_id}")
            return order_id
        else:
            logger.error(f"[{symbol}] Place market order error: {result.get('retMsg')}")
            return None
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """Obține prețul curent pentru un simbol"""
        endpoint = "/v5/market/tickers"
        params = {
            "category": "linear",
            "symbol": symbol
        }
        
        result = await self._request("GET", endpoint, params)
        
        if result.get("retCode") == 0:
            tickers = result.get("result", {}).get("list", [])
            if tickers:
                return tickers[0]
            else:
                logger.warning(f"[{symbol}] No ticker data in response, using fallback")
        else:
            logger.warning(f"[{symbol}] Get ticker failed: {result.get('retMsg')}, using fallback")
        
        return {}
