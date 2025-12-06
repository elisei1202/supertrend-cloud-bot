import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.web import router
from app.trading import bot_controller
from app.config import settings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager - startup and shutdown"""
    # Startup
    logger.info("🚀 Starting SuperTrend Cloud Bot...")
    logger.info(f"Symbols: {settings.symbol_list}")
    logger.info(f"Timeframe: {settings.TIMEFRAME}m ({settings.timeframe_display})")
    logger.info(f"Leverage: {settings.LEVERAGE}x ISOLATED")
    logger.info(f"Position Size: {settings.POSITION_SIZE_USDT} USDT")
    
    # Start bot controller
    await bot_controller.start()
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down bot...")
    await bot_controller.stop()


# Create FastAPI app
app = FastAPI(
    title="SuperTrend Cloud Trading Bot",
    description="Automated trading bot for Bybit Unified Futures USDT",
    version="1.0.0",
    lifespan=lifespan
)

# Include routes
app.include_router(router)

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "bot_running": bot_controller.is_running
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
