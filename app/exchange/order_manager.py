import asyncio
import math
import logging
from typing import Optional
from app.exchange.bybit_client import BybitClient
from app.config import settings

logger = logging.getLogger(__name__)


class OrderManager:
    """Gestionează ordinele și calculul cantităților"""
    
    def __init__(self, client: BybitClient):
        self.client = client
        self.instruments_cache = {}
    
    async def get_instrument_info(self, symbol: str) -> dict:
        """Obține și cache-uiește instrument info"""
        if symbol not in self.instruments_cache:
            info = await self.client.get_instruments_info(symbol)
            if info:
                self.instruments_cache[symbol] = info
                logger.debug(f"[{symbol}] Instrument info cached")
            else:
                logger.warning(f"[{symbol}] Failed to get instrument info, using defaults")
                return {}
        return self.instruments_cache.get(symbol, {})
    
    def adjust_quantity(
        self,
        qty: float,
        qty_step: float,
        min_qty: float,
        max_qty: float
    ) -> float:
        """Ajustează cantitatea conform stepSize și limitelor"""
        # Round to step size with proper precision
        if qty_step > 0:
            # Determine decimals from step size
            step_str = f"{qty_step:.10f}".rstrip('0')
            if '.' in step_str:
                decimals = len(step_str.split('.')[-1])
            else:
                decimals = 0
            
            # Floor to step size
            qty = math.floor(qty / qty_step) * qty_step
            
            # Round to avoid floating point issues
            qty = round(qty, decimals)
        
        # Apply limits
        qty = max(min_qty, min(qty, max_qty))
        
        return qty
    
    async def calculate_order_qty(
        self,
        symbol: str,
        notional_usdt: float,
        current_price: float
    ) -> Optional[float]:
        """
        Calculează cantitatea pentru o ordine bazat pe notional USDT
        
        Args:
            symbol: Trading symbol
            notional_usdt: Suma în USDT pentru trade
            current_price: Prețul curent
        
        Returns:
            Cantitatea ajustată sau None dacă nu se poate calcula
        """
        info = await self.get_instrument_info(symbol)
        
        if not info:
            logger.error(f"[{symbol}] Cannot calculate qty - no instrument info available")
            return None
        
        lot_size = info.get("lotSizeFilter", {})
        qty_step = float(lot_size.get("qtyStep", "0.001"))
        min_qty = float(lot_size.get("minOrderQty", "0.001"))
        max_qty = float(lot_size.get("maxOrderQty", "1000"))
        min_notional = float(lot_size.get("minNotionalValue", "5"))
        
        # Calculate base quantity
        qty = notional_usdt / current_price
        
        # Adjust to step size
        qty = self.adjust_quantity(qty, qty_step, min_qty, max_qty)
        
        # Verify min notional
        actual_notional = qty * current_price
        if actual_notional < min_notional:
            logger.warning(f"[{symbol}] Notional {actual_notional:.2f} < min {min_notional}, adjusting qty")
            # Try to adjust
            qty = min_notional / current_price
            qty = self.adjust_quantity(qty, qty_step, min_qty, max_qty)
        
        logger.info(f"[{symbol}] Calculated qty: {qty} (notional: {qty * current_price:.2f} USDT)")
        return qty
    
    async def open_long(self, symbol: str, price: float) -> bool:
        """Deschide poziție LONG"""
        qty = await self.calculate_order_qty(symbol, settings.POSITION_SIZE_USDT, price)
        if qty is None:
            logger.error(f"[{symbol}] Failed to calculate qty for LONG")
            return False
        
        order_id = await self.client.place_market_order(
            symbol=symbol,
            side="Buy",
            qty=qty,
            reduce_only=False
        )
        
        success = order_id is not None
        if not success:
            logger.error(f"[{symbol}] Failed to open LONG position")
        return success
    
    async def open_short(self, symbol: str, price: float) -> bool:
        """Deschide poziție SHORT"""
        qty = await self.calculate_order_qty(symbol, settings.POSITION_SIZE_USDT, price)
        if qty is None:
            logger.error(f"[{symbol}] Failed to calculate qty for SHORT")
            return False
        
        order_id = await self.client.place_market_order(
            symbol=symbol,
            side="Sell",
            qty=qty,
            reduce_only=False
        )
        
        success = order_id is not None
        if not success:
            logger.error(f"[{symbol}] Failed to open SHORT position")
        return success
    
    async def close_position(self, symbol: str, current_qty: float, side: str) -> bool:
        """
        Închide o poziție existentă
        
        Args:
            symbol: Trading symbol
            current_qty: Cantitatea curentă a poziției (pozitivă)
            side: "LONG" sau "SHORT"
        """
        if current_qty <= 0:
            logger.warning(f"[{symbol}] No position to close (qty={current_qty})")
            return False
        
        # Pentru LONG, vindem (Sell cu reduce_only)
        # Pentru SHORT, cumpărăm (Buy cu reduce_only)
        order_side = "Sell" if side == "LONG" else "Buy"
        
        order_id = await self.client.place_market_order(
            symbol=symbol,
            side=order_side,
            qty=current_qty,
            reduce_only=True
        )
        
        success = order_id is not None
        if not success:
            logger.error(f"[{symbol}] Failed to close {side} position")
        return success
    
    async def reverse_position(
        self,
        symbol: str,
        current_qty: float,
        current_side: str,
        new_side: str,
        price: float
    ) -> bool:
        """
        Reverse poziție: închide poziția curentă și deschide în direcția opusă
        
        Args:
            symbol: Trading symbol
            current_qty: Cantitatea poziției curente
            current_side: "LONG" sau "SHORT"
            new_side: "LONG" sau "SHORT" (direcția nouă)
            price: Prețul curent
        """
        # Închide poziția curentă
        close_success = await self.close_position(symbol, current_qty, current_side)
        
        if not close_success:
            logger.error(f"[{symbol}] Failed to close {current_side} position during reverse")
            return False
        
        # Așteaptă un moment pentru procesarea ordinului
        await asyncio.sleep(0.5)
        
        # Deschide poziția nouă
        if new_side == "LONG":
            open_success = await self.open_long(symbol, price)
        else:
            open_success = await self.open_short(symbol, price)
        
        if not open_success:
            logger.error(f"[{symbol}] Failed to open {new_side} position during reverse (close was successful)")
        
        return open_success
