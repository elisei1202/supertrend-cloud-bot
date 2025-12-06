import logging
from typing import Literal, Tuple
from app.models import PositionState
from app.exchange.order_manager import OrderManager
from app.config import settings

logger = logging.getLogger(__name__)


class StateMachine:
    """
    State Machine pentru strategia SuperTrend Cloud
    
    Implementează logica completă:
    - Crossover Cloud (UNDER → OVER): Open/Reverse LONG
    - Crossunder Cloud (OVER → UNDER): Open/Reverse SHORT
    - Exit from Cloud (IN → OVER): Open LONG (dacă FLAT)
    - Exit from Cloud (IN → UNDER): Open SHORT (dacă FLAT)
    - Enter Cloud (any → IN): Close position
    """
    
    def __init__(self, order_manager: OrderManager):
        self.order_manager = order_manager
    
    def _calculate_expected_qty(self, price: float) -> float:
        """Calculează qty așteptat bazat pe POSITION_SIZE_USDT și preț"""
        if price <= 0:
            return 0.0
        return settings.POSITION_SIZE_USDT / price
    
    async def process_signal(
        self,
        state: PositionState,
        current_zone: Literal["OVER", "UNDER", "IN"],
        current_price: float,
        trading_enabled: bool
    ) -> Tuple[bool, str]:
        """
        Procesează semnalul și execută ordinele corespunzătoare
        
        Args:
            state: State-ul curent al poziției pentru simbol
            current_zone: Zona curentă (OVER/UNDER/IN)
            current_price: Prețul curent
            trading_enabled: Dacă trading este activat
        
        Returns:
            (success: bool, signal_message: str)
        """
        prev_zone = state.prev_zone
        pos_state = state.pos_state
        symbol = state.symbol
        
        signal = "No signal"
        success = True
        
        # Skip dacă este prima iterație (prev_zone == NONE)
        if prev_zone == "NONE":
            state.current_zone = current_zone
            state.prev_zone = current_zone
            logger.info(f"[{symbol}] Initializing with zone: {current_zone}")
            return True, "Initializing"
        
        # Dacă zona nu s-a schimbat, nu facem nimic
        if prev_zone == current_zone:
            state.current_zone = current_zone
            state.last_signal = "Holding"
            return True, "Holding"
        
        # === TRANZIȚII CARE DESCHID LONG ===
        # 1. CROSSOVER CLOUD: UNDER → OVER
        # 2. EXIT CLOUD UP: IN → OVER (doar dacă FLAT)
        if current_zone == "OVER" and prev_zone in ["UNDER", "IN"]:
            if prev_zone == "UNDER":
                signal = "Crossover Cloud → "
            else:
                signal = "Exit Cloud Up → "
            
            if pos_state == "FLAT":
                signal += "Open LONG"
                if trading_enabled:
                    success = await self.order_manager.open_long(symbol, current_price)
                    if success:
                        state.pos_state = "LONG"
                        state.entry_price = current_price
                        # Estimează qty (va fi actualizat din exchange la următoarea iterație)
                        state.qty = self._calculate_expected_qty(current_price)
                        logger.info(f"[{symbol}] Opened LONG at {current_price}")
                    else:
                        # Order failed - DO NOT update state
                        logger.error(f"[{symbol}] Failed to open LONG - state unchanged")
                        signal += " (FAILED)"
                else:
                    logger.info(f"[{symbol}] {signal} (Trading disabled)")
            
            elif pos_state == "SHORT" and prev_zone == "UNDER":
                # Reverse doar la crossover complet (UNDER → OVER), nu din IN
                signal += "Reverse SHORT → LONG"
                if trading_enabled:
                    # Folosește qty din state, dar dacă e 0, estimează
                    qty_to_close = state.qty if state.qty > 0 else self._calculate_expected_qty(current_price)
                    success = await self.order_manager.reverse_position(
                        symbol=symbol,
                        current_qty=qty_to_close,
                        current_side="SHORT",
                        new_side="LONG",
                        price=current_price
                    )
                    if success:
                        state.pos_state = "LONG"
                        state.entry_price = current_price
                        state.qty = self._calculate_expected_qty(current_price)
                        logger.info(f"[{symbol}] Reversed SHORT → LONG at {current_price}")
                    else:
                        # Reverse failed - state might be inconsistent, will be corrected by exchange sync
                        logger.error(f"[{symbol}] Failed to reverse SHORT → LONG - state will be synced from exchange")
                        signal += " (FAILED)"
                else:
                    logger.info(f"[{symbol}] {signal} (Trading disabled)")
        
        # === TRANZIȚII CARE DESCHID SHORT ===
        # 1. CROSSUNDER CLOUD: OVER → UNDER
        # 2. EXIT CLOUD DOWN: IN → UNDER (doar dacă FLAT)
        elif current_zone == "UNDER" and prev_zone in ["OVER", "IN"]:
            if prev_zone == "OVER":
                signal = "Crossunder Cloud → "
            else:
                signal = "Exit Cloud Down → "
            
            if pos_state == "FLAT":
                signal += "Open SHORT"
                if trading_enabled:
                    success = await self.order_manager.open_short(symbol, current_price)
                    if success:
                        state.pos_state = "SHORT"
                        state.entry_price = current_price
                        state.qty = self._calculate_expected_qty(current_price)
                        logger.info(f"[{symbol}] Opened SHORT at {current_price}")
                    else:
                        # Order failed - DO NOT update state
                        logger.error(f"[{symbol}] Failed to open SHORT - state unchanged")
                        signal += " (FAILED)"
                else:
                    logger.info(f"[{symbol}] {signal} (Trading disabled)")
            
            elif pos_state == "LONG" and prev_zone == "OVER":
                # Reverse doar la crossunder complet (OVER → UNDER), nu din IN
                signal += "Reverse LONG → SHORT"
                if trading_enabled:
                    qty_to_close = state.qty if state.qty > 0 else self._calculate_expected_qty(current_price)
                    success = await self.order_manager.reverse_position(
                        symbol=symbol,
                        current_qty=qty_to_close,
                        current_side="LONG",
                        new_side="SHORT",
                        price=current_price
                    )
                    if success:
                        state.pos_state = "SHORT"
                        state.entry_price = current_price
                        state.qty = self._calculate_expected_qty(current_price)
                        logger.info(f"[{symbol}] Reversed LONG → SHORT at {current_price}")
                    else:
                        # Reverse failed - state might be inconsistent, will be corrected by exchange sync
                        logger.error(f"[{symbol}] Failed to reverse LONG → SHORT - state will be synced from exchange")
                        signal += " (FAILED)"
                else:
                    logger.info(f"[{symbol}] {signal} (Trading disabled)")
        
        # === INTRARE ÎN CLOUD: Închide orice poziție ===
        elif current_zone == "IN" and prev_zone in ["OVER", "UNDER"]:
            if pos_state in ["LONG", "SHORT"]:
                signal = f"Enter Cloud → Close {pos_state}"
                if trading_enabled:
                    qty_to_close = state.qty if state.qty > 0 else self._calculate_expected_qty(current_price)
                    if qty_to_close > 0:
                        success = await self.order_manager.close_position(
                            symbol=symbol,
                            current_qty=qty_to_close,
                            side=pos_state
                        )
                        if success:
                            state.pos_state = "FLAT"
                            state.entry_price = 0.0
                            state.qty = 0.0
                            logger.info(f"[{symbol}] Closed {pos_state} position")
                        else:
                            # Close failed - DO NOT update state
                            logger.error(f"[{symbol}] Failed to close {pos_state} - state unchanged")
                            signal += " (FAILED)"
                    else:
                        logger.warning(f"[{symbol}] Cannot close - qty is 0")
                        success = False
                        signal += " (NO QTY)"
                else:
                    logger.info(f"[{symbol}] {signal} (Trading disabled)")
            else:
                signal = "Enter Cloud (already FLAT)"
        
        # Update zone state ONLY if order was successful or no order was attempted
        # This prevents zone desync when orders fail
        if success:
            state.current_zone = current_zone
            state.prev_zone = current_zone
            state.last_signal = signal
        else:
            # On failure, update only signal to track what happened
            # Keep prev_zone unchanged so retry is possible on next candle
            state.current_zone = current_zone
            state.last_signal = signal
            logger.warning(f"[{symbol}] Order failed - prev_zone kept as {prev_zone} for potential retry")
        
        return success, signal
