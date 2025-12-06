import asyncio
import logging
import pandas as pd
from datetime import datetime
from typing import Dict
from app.exchange import BybitClient, OrderManager
from app.strategy import StateMachine
from app.indicators import calculate_supertrend_cloud, get_zone
from app.models import trading_state, PositionState
from app.config import settings

logger = logging.getLogger(__name__)


class BotController:
    """Controller principal pentru trading bot"""
    
    def __init__(self):
        self.client = BybitClient()
        self.order_manager = OrderManager(self.client)
        self.state_machine = StateMachine(self.order_manager)
        self.is_running = False
        self.last_candle_times: Dict[str, int] = {}
        self.loop_iteration = 0
    
    async def initialize(self):
        """Inițializează botul: setează leverage și margin mode pentru toate simbolurile"""
        logger.info("Initializing bot...")
        
        init_errors = []
        
        for symbol in settings.symbol_list:
            try:
                # Set leverage (margin mode not needed for Unified Account)
                leverage_ok = await self.client.set_leverage(symbol, settings.LEVERAGE)
                await asyncio.sleep(0.2)
                
                if leverage_ok:
                    logger.info(f"[{symbol}] Initialized with {settings.LEVERAGE}x leverage")
                else:
                    init_errors.append(symbol)
                    logger.warning(f"[{symbol}] Failed to set leverage")
                    
            except Exception as e:
                init_errors.append(symbol)
                logger.error(f"[{symbol}] Initialization error: {type(e).__name__}: {e}")
        
        if init_errors:
            logger.warning(f"Initialization issues for: {init_errors}")
        
        # Test connection
        try:
            ticker = await self.client.get_ticker(settings.symbol_list[0])
            if ticker:
                trading_state.connection_ok = True
                logger.info("✅ Connection to Bybit OK")
            else:
                trading_state.connection_ok = False
                logger.error("❌ Connection to Bybit FAILED - no ticker data")
        except Exception as e:
            trading_state.connection_ok = False
            logger.error(f"❌ Connection test failed: {type(e).__name__}: {e}")
    
    async def fetch_and_process_klines(self, symbol: str) -> pd.DataFrame:
        """Fetch klines și convertește în DataFrame"""
        klines = await self.client.get_klines(
            symbol=symbol,
            interval=settings.TIMEFRAME,
            limit=settings.CANDLES_LIMIT
        )
        
        if not klines:
            logger.error(f"[{symbol}] No klines received from Bybit (empty list)")
            return pd.DataFrame()
        
        logger.info(f"[{symbol}] Received {len(klines)} klines from Bybit for timeframe={settings.TIMEFRAME}")
        
        # Extract first and last timestamp for logging
        first_ts = int(klines[0][0]) // 1000
        last_ts = int(klines[-1][0]) // 1000
        first_dt = datetime.utcfromtimestamp(first_ts)
        last_dt = datetime.utcfromtimestamp(last_ts)
        logger.info(f"[{symbol}] Klines range: first_ts={first_ts} ({first_dt} UTC) | last_ts={last_ts} ({last_dt} UTC)")
        
        # Convert to DataFrame
        # Bybit returns: [startTime, openPrice, highPrice, lowPrice, closePrice, volume, turnover]
        df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'])
        
        # Convert types
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        df['open'] = pd.to_numeric(df['open'])
        df['high'] = pd.to_numeric(df['high'])
        df['low'] = pd.to_numeric(df['low'])
        df['close'] = pd.to_numeric(df['close'])
        df['volume'] = pd.to_numeric(df['volume'])
        
        # Sort by timestamp ascending (oldest first)
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        return df
    
    async def update_position_from_exchange(self, symbol: str) -> bool:
        """
        Actualizează state-ul poziției din exchange
        
        Returns:
            True dacă sync a reușit, False dacă a eșuat
        """
        try:
            positions = await self.client.get_positions(symbol)
        except Exception as e:
            logger.error(f"[{symbol}] Failed to get positions from exchange: {type(e).__name__}: {e}")
            return False
        
        state = trading_state.get_position(symbol)
        
        if positions:
            pos = positions[0]
            # Handle empty strings from API
            size_str = pos.get('size', '0') or '0'
            entry_str = pos.get('avgPrice', '0') or '0'
            pnl_str = pos.get('unrealisedPnl', '0') or '0'
            
            size = float(size_str)
            side = pos.get('side', '')
            entry_price = float(entry_str)
            unrealized_pnl = float(pnl_str)
            
            if size > 0:
                new_state = "LONG" if side == "Buy" else "SHORT"
                
                # Log if state changed
                if state.pos_state != new_state or abs(state.qty - size) > 0.0001:
                    logger.info(f"[{symbol}] Position sync: {state.pos_state}({state.qty}) → {new_state}({size})")
                
                state.qty = size
                state.pos_state = new_state
                state.entry_price = entry_price
                state.unrealized_pnl = unrealized_pnl
            else:
                if state.pos_state != "FLAT":
                    logger.info(f"[{symbol}] Position sync: {state.pos_state} → FLAT")
                
                state.pos_state = "FLAT"
                state.qty = 0.0
                state.entry_price = 0.0
                state.unrealized_pnl = 0.0
        else:
            # No positions returned - could be FLAT or API issue
            # Only reset if we had a position before
            if state.pos_state != "FLAT":
                logger.warning(f"[{symbol}] No position data returned, assuming FLAT")
                state.pos_state = "FLAT"
                state.qty = 0.0
                state.entry_price = 0.0
                state.unrealized_pnl = 0.0
        
        return True
    
    async def process_symbol(self, symbol: str):
        """Procesează un simbol: fetch data, calculate indicators, run state machine"""
        try:
            logger.info(f"[{symbol}] ===== Process symbol START =====")
            
            # Fetch klines
            df = await self.fetch_and_process_klines(symbol)
            
            if df.empty:
                logger.warning(f"[{symbol}] Empty DataFrame after fetch_and_process_klines → skipping symbol")
                return
            
            if len(df) < 50:
                logger.warning(f"[{symbol}] Insufficient candles: {len(df)} < 50 → skipping symbol")
                return
            
            # Check if new candle closed
            latest_candle_time = int(df.iloc[-1]['timestamp'])
            latest_dt_utc = datetime.utcfromtimestamp(latest_candle_time / 1000.0)
            logger.info(f"[{symbol}] Latest candle timestamp={latest_candle_time} ({latest_dt_utc} UTC)")
            
            if symbol in self.last_candle_times:
                if latest_candle_time == self.last_candle_times[symbol]:
                    prev_dt_utc = datetime.utcfromtimestamp(self.last_candle_times[symbol] / 1000.0)
                    logger.info(f"[{symbol}] Same closed candle as last run ({latest_candle_time} / {prev_dt_utc} UTC) → skipping update")
                    return
                else:
                    prev_dt_utc = datetime.utcfromtimestamp(self.last_candle_times[symbol] / 1000.0)
                    logger.info(f"[{symbol}] New closed candle detected: prev_ts={self.last_candle_times[symbol]} ({prev_dt_utc} UTC) → new_ts={latest_candle_time} ({latest_dt_utc} UTC)")
            
            self.last_candle_times[symbol] = latest_candle_time
            logger.info(f"[{symbol}] last_candle_times updated to {latest_candle_time} ({latest_dt_utc} UTC)")
            
            # Calculate SuperTrend Cloud
            upper_cloud, lower_cloud = calculate_supertrend_cloud(
                df=df,
                st1_period=settings.ST1_PERIOD,
                st1_multiplier=settings.ST1_MULTIPLIER,
                st2_period=settings.ST2_PERIOD,
                st2_multiplier=settings.ST2_MULTIPLIER
            )
            
            # Get current close and zone
            current_close = df.iloc[-1]['close']
            current_upper = upper_cloud.iloc[-1]
            current_lower = lower_cloud.iloc[-1]
            current_zone = get_zone(current_close, current_upper, current_lower)
            logger.info(f"[{symbol}] SuperTrend Cloud zone={current_zone} | close={current_close} | upper={current_upper} | lower={current_lower}")
            
            # Get current price (ticker) with fallback
            ticker = await self.client.get_ticker(symbol)
            if ticker:
                current_price = float(ticker.get('lastPrice', current_close))
            else:
                logger.warning(f"[{symbol}] Using candle close as fallback price")
                current_price = current_close
            logger.info(f"[{symbol}] Using current_price={current_price} (ticker fallback={'YES' if not ticker else 'NO'})")
            
            # Update position from exchange BEFORE processing signal
            logger.info(f"[{symbol}] Syncing position from exchange BEFORE state machine...")
            sync_ok = await self.update_position_from_exchange(symbol)
            if not sync_ok:
                logger.warning(f"[{symbol}] Position sync failed, proceeding with cached state")
            
            # Get position state
            state = trading_state.get_position(symbol)
            state.current_zone = current_zone
            state.last_candle_time = latest_candle_time
            state.last_update = datetime.now()
            logger.info(f"[{symbol}] State timestamp updated: last_candle_time={state.last_candle_time} | last_update={state.last_update.isoformat()}")
            
            # Run state machine
            success, signal = await self.state_machine.process_signal(
                state=state,
                current_zone=current_zone,
                current_price=current_price,
                trading_enabled=trading_state.trading_enabled
            )
            logger.info(f"[{symbol}] StateMachine result: success={success} | signal='{signal}' | pos_state={state.pos_state} | qty={state.qty}")
            
            # Update position from exchange AFTER order execution if there was a trade signal
            if signal not in ["No signal", "Holding", "Initializing"]:
                logger.info(f"[{symbol}] Trade signal detected ('{signal}') → waiting 1s then resyncing position from exchange...")
                await asyncio.sleep(1.0)  # Wait for order to fill
                post_sync_ok = await self.update_position_from_exchange(symbol)
                logger.info(f"[{symbol}] Post-trade position sync result: {post_sync_ok}")
                if not post_sync_ok:
                    logger.warning(f"[{symbol}] Post-trade position sync failed")
            
            logger.info(f"[{symbol}] Zone: {current_zone} | State: {state.pos_state} | Signal: {signal}")
            logger.info(f"[{symbol}] ===== Process symbol END =====")
            
        except Exception as e:
            logger.error(f"[{symbol}] Processing error: {type(e).__name__}: {e}", exc_info=True)
    
    async def trading_loop(self):
        """Main trading loop - procesează toate simbolurile"""
        logger.info("🚀 Trading loop started")
        logger.info(f"[Loop] Starting trading loop | timeframe={settings.TIMEFRAME} | symbols={settings.symbol_list}")
        
        iteration = 0
        
        while self.is_running:
            try:
                iteration += 1
                self.loop_iteration = iteration
                logger.info(f"[Loop] Iteration #{iteration} started at {datetime.now().isoformat()}")
                
                # Process all symbols in parallel
                tasks = [self.process_symbol(symbol) for symbol in settings.symbol_list]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Count successful and log exceptions
                successful = sum(1 for r in results if not isinstance(r, Exception))
                logger.info(f"[Loop] Iteration #{iteration} finished | processed={successful}/{len(settings.symbol_list)} symbols")
                
                # Log any exceptions
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        symbol = settings.symbol_list[i]
                        logger.error(f"[{symbol}] Task exception: {type(result).__name__}: {result}")
                
                # Wait before next iteration (check every 60 seconds for new candles)
                await asyncio.sleep(60)
                
            except asyncio.CancelledError:
                logger.info("Trading loop cancelled")
                break
            except Exception as e:
                logger.error(f"[Loop] Fatal error in trading_loop: {type(e).__name__}: {e}")
                await asyncio.sleep(60)
        
        logger.info("🛑 Trading loop stopped")
    
    async def start(self):
        """Pornește botul"""
        if self.is_running:
            logger.warning("Bot is already running")
            return
        
        self.is_running = True
        await self.initialize()
        
        # Start trading loop in background
        asyncio.create_task(self.trading_loop())
    
    async def stop(self):
        """Oprește botul"""
        logger.info("Stopping bot...")
        self.is_running = False
    
    async def force_close_all(self):
        """Închide forțat toate pozițiile active"""
        logger.warning("⚠️ Force closing all positions...")
        
        closed_count = 0
        failed_count = 0
        
        for symbol in settings.symbol_list:
            try:
                # First sync with exchange to get accurate position
                await self.update_position_from_exchange(symbol)
                
                state = trading_state.get_position(symbol)
                
                if state.pos_state != "FLAT" and state.qty > 0:
                    success = await self.order_manager.close_position(
                        symbol=symbol,
                        current_qty=state.qty,
                        side=state.pos_state
                    )
                    
                    if success:
                        state.pos_state = "FLAT"
                        state.qty = 0.0
                        state.entry_price = 0.0
                        state.unrealized_pnl = 0.0
                        logger.info(f"[{symbol}] Position closed successfully")
                        closed_count += 1
                    else:
                        logger.error(f"[{symbol}] Failed to close position")
                        failed_count += 1
                
            except Exception as e:
                logger.error(f"[{symbol}] Force close error: {type(e).__name__}: {e}")
                failed_count += 1
        
        logger.info(f"✅ Force close completed: {closed_count} closed, {failed_count} failed")


# Global bot instance
bot_controller = BotController()