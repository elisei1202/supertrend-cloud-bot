from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.models import trading_state
from app.trading import bot_controller
from app.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Dashboard principal - desktop view"""
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "timeframe": "4h",
        "candles": settings.CANDLES_LIMIT,
        "leverage": settings.LEVERAGE
    })


@router.get("/mobile", response_class=HTMLResponse)
async def mobile_view(request: Request):
    """Mobile optimized view"""
    return templates.TemplateResponse("mobile.html", {
        "request": request,
        "leverage": settings.LEVERAGE
    })


@router.get("/config", response_class=HTMLResponse)
async def config_page(request: Request):
    """Configuration page"""
    return templates.TemplateResponse("config.html", {
        "request": request,
        "settings": {
            "symbols": settings.SYMBOLS,
            "position_size": settings.POSITION_SIZE_USDT,
            "leverage": settings.LEVERAGE,
            "st1_period": settings.ST1_PERIOD,
            "st1_multiplier": settings.ST1_MULTIPLIER,
            "st2_period": settings.ST2_PERIOD,
            "st2_multiplier": settings.ST2_MULTIPLIER
        }
    })


# API Endpoints

@router.get("/api/status")
async def get_status():
    """Get global status"""
    return {
        "trading_enabled": trading_state.trading_enabled,
        "connection_ok": trading_state.connection_ok,
        "timeframe": "4h",
        "candles_used": settings.CANDLES_LIMIT,
        "bot_running": bot_controller.is_running
    }


@router.get("/api/positions")
async def get_positions():
    """Get all positions"""
    positions = []
    
    for symbol in settings.symbol_list:
        state = trading_state.get_position(symbol)
        positions.append({
            "symbol": symbol,
            "pos_state": state.pos_state,
            "qty": state.qty,
            "entry_price": state.entry_price,
            "unrealized_pnl": state.unrealized_pnl,
            "zone": state.current_zone,
            "last_signal": state.last_signal,
            "last_update": state.last_update.isoformat() if state.last_update else None
        })
    
    return {"positions": positions}


@router.post("/api/trading/start")
async def start_trading():
    """Start trading (enable trade execution)"""
    trading_state.trading_enabled = True
    
    # Ensure bot is running
    if not bot_controller.is_running:
        await bot_controller.start()
    
    return {"status": "success", "trading_enabled": True}


@router.post("/api/trading/stop")
async def stop_trading():
    """Stop trading (disable trade execution, but keep bot running)"""
    trading_state.trading_enabled = False
    return {"status": "success", "trading_enabled": False}


@router.post("/api/trading/force-close-all")
async def force_close_all():
    """Force close all positions"""
    try:
        await bot_controller.force_close_all()
        return {"status": "success", "message": "All positions closed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/api/config/update")
async def update_config(data: dict):
    """Update configuration and restart bot to apply changes"""
    try:
        # Update settings directly
        if "symbols" in data:
            settings.SYMBOLS = data["symbols"]
        if "position_size" in data:
            settings.POSITION_SIZE_USDT = float(data["position_size"])
        if "leverage" in data:
            settings.LEVERAGE = int(data["leverage"])
        if "st1_period" in data:
            settings.ST1_PERIOD = int(data["st1_period"])
        if "st1_multiplier" in data:
            settings.ST1_MULTIPLIER = float(data["st1_multiplier"])
        if "st2_period" in data:
            settings.ST2_PERIOD = int(data["st2_period"])
        if "st2_multiplier" in data:
            settings.ST2_MULTIPLIER = float(data["st2_multiplier"])
        
        # Restart bot to apply new settings
        await bot_controller.restart()
        
        return {
            "status": "success",
            "message": "Configuration updated and bot restarted successfully."
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Error updating configuration: {str(e)}"
        }
