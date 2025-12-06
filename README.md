# 🚀 SuperTrend Cloud Trading Bot

Bot automat de trading pentru **Bybit Unified Futures USDT** care implementează strategia **SuperTrend Cloud** 1:1 din TradingView.

## 📋 Caracteristici

- ✅ **Strategie SuperTrend Cloud** (crossover/crossunder/in cloud logic)
- ✅ **Bybit Unified Futures USDT** (cont LIVE, nu testnet)
- ✅ **20x Leverage ISOLATED** pentru toate simbolurile
- ✅ **5 Simboluri** din top: BTC, ETH, BNB, SOL, XRP
- ✅ **Timeframe 4h** cu minimum 400 lumânări per calcul
- ✅ **Asincron complet** - procesare paralelă a simbolurilor
- ✅ **Web UI modern** - dashboard desktop + pagină mobilă
- ✅ **Trading toggle** - activează/dezactivează tranzacțiile fără restart
- ✅ **Force close** - închide toate pozițiile instant
- ✅ **Deploy simplu** pe Render free (Frankfurt)

## 🎯 Strategia SuperTrend Cloud

### Logică 1:1:

```
Două SuperTrend-uri formează un "cloud":
- ST1: Period 10, Multiplier 3.0
- ST2: Period 10, Multiplier 6.0

Upper Cloud = max(ST1, ST2)
Lower Cloud = min(ST1, ST2)

Zone:
- OVER: close > upper_cloud
- UNDER: close < lower_cloud  
- IN: lower_cloud ≤ close ≤ upper_cloud

Semnale:
1. Crossover Cloud (UNDER → OVER):
   - FLAT → Open LONG
   - SHORT → Reverse to LONG
   
2. Crossunder Cloud (OVER → UNDER):
   - FLAT → Open SHORT
   - LONG → Reverse to SHORT
   
3. In Cloud:
   - Close orice poziție activă
```

## 🏗️ Structură Proiect

```
supertrend-cloud-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app + startup
│   ├── config.py               # Configurare centralizată
│   ├── models.py               # State management
│   │
│   ├── indicators/
│   │   └── supertrend_cloud.py # ST calculation
│   │
│   ├── exchange/
│   │   ├── bybit_client.py     # Async Bybit V5 client
│   │   └── order_manager.py    # Orders & qty calculation
│   │
│   ├── strategy/
│   │   └── state_machine.py    # Trading logic
│   │
│   ├── trading/
│   │   └── bot_controller.py   # Main trading loop
│   │
│   └── web/
│       ├── routes.py           # API endpoints
│       └── templates/          # HTML UI
│           ├── dashboard.html  # Desktop view
│           ├── mobile.html     # Mobile view
│           └── config.html     # Settings
│
├── requirements.txt
├── render.yaml                 # Render blueprint
├── .env.example
└── README.md
```

## 🚀 Deploy pe Render

### 1. Pregătire

1. Creează cont pe [Render.com](https://render.com)
2. Obține API keys de la Bybit:
   - Mergi la Bybit → API Management
   - Creează API key cu permisiuni: **Trading** (Unified Account)
   - Salvează API Key și Secret

### 2. Deploy cu Blueprint

1. Push codul pe GitHub
2. Pe Render: **New** → **Blueprint**
3. Conectează repo-ul
4. Render va detecta `render.yaml` automat
5. **IMPORTANT**: Setează variabilele de mediu:
   - `BYBIT_API_KEY`: cheia ta API
   - `BYBIT_API_SECRET`: secretul tău API

### 3. Deploy Manual (alternativ)

1. Pe Render: **New** → **Web Service**
2. Conectează repo
3. Setări:
   - **Runtime**: Python 3
   - **Region**: Frankfurt
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Variabile de mediu:
   - `BYBIT_API_KEY`
   - `BYBIT_API_SECRET`
   - `SYMBOLS`: BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT
   - `POSITION_SIZE_USDT`: 10
   - `LEVERAGE`: 20
   - Restul au valori default în cod

## 💻 Rulare Locală

```bash
# Clone repo
git clone <repo-url>
cd supertrend-cloud-bot

# Creează virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Instalează dependințe
pip install -r requirements.txt

# Configurează .env
cp .env.example .env
# Editează .env cu API keys

# Rulează
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Acces UI: `http://localhost:8000`

## 🎨 Interfață Web

### Desktop Dashboard (`/`)
- Status global (trading ON/OFF, connection)
- Control panel (start/stop trading, force close all)
- Tabel cu toate pozițiile
- Info în timp real

### Mobile View (`/mobile`)
- Layout optimizat pentru telefon
- Cards verticale pentru fiecare simbol
- Toggle mare pentru trading
- Ușor de folosit cu degetul

### Config Page (`/config`)
- Modificare simboluri
- Ajustare position size, leverage
- Parametri SuperTrend personalizabili

## 📊 Parametri Configurabili

| Parametru | Default | Descriere |
|-----------|---------|-----------|
| SYMBOLS | BTC,ETH,BNB,SOL,XRP | Simboluri trade |
| POSITION_SIZE_USDT | 10 | USDT per trade |
| LEVERAGE | 20 | Leverage ISOLATED |
| TIMEFRAME | 240 | 4h (minute) |
| CANDLES_LIMIT | 400 | Lumânări pentru calcul |
| ST1_PERIOD | 10 | SuperTrend 1 period |
| ST1_MULTIPLIER | 3.0 | SuperTrend 1 multiplier |
| ST2_PERIOD | 10 | SuperTrend 2 period |
| ST2_MULTIPLIER | 6.0 | SuperTrend 2 multiplier |

## ⚙️ Funcționalități UI

### Trading Control
- **Start Trading**: Activează execuția ordinelor
- **Stop Trading**: Suspendă ordinele (botul continuă să ruleze, calculează indicatori, dar NU plasează ordine)
- **Force Close All**: Închide instant toate pozițiile active

### Live Updates
- Status actualizat la fiecare 5 secunde
- Poziții actualizate la fiecare 3 secunde
- Auto-refresh pentru date în timp real

## 🔒 Securitate

- API keys NICIODATĂ în cod
- Toate credențialele în variabile de mediu
- HMAC SHA256 signature pentru toate request-urile către Bybit
- Connections HTTPS only

## 📝 Loguri

Botul afișează loguri detaliate:
- ✅ Conexiuni la Bybit
- 📊 Calculare indicatori
- 💹 Semnale de trading
- 📈 Execuție ordine
- ⚠️ Erori și warnings

## 🐛 Troubleshooting

**Bot nu se conectează la Bybit:**
- Verifică API keys (BYBIT_API_KEY, BYBIT_API_SECRET)
- Verifică că API key are permisiuni pentru Unified Trading

**Ordinele nu se execută:**
- Verifică că `trading_enabled = TRUE` în UI
- Verifică balanța USDT în cont
- Verifică logurile pentru erori

**Deployment pe Render eșuează:**
- Verifică că toate env vars sunt setate
- Verifică logurile de build pe Render
- Asigură-te că `render.yaml` este corect configurat

## 📚 Resurse

- [Bybit API V5 Documentation](https://bybit-exchange.github.io/docs/v5/intro)
- [SuperTrend Cloud Strategy (TradingView)](https://www.tradingview.com/script/sO5mkXTE-SuperTrend-Cloud-Strategy/)
- [Render Deployment Docs](https://render.com/docs)

## 🎯 Stack Tehnologic

- **Backend**: FastAPI (Python async)
- **Exchange API**: Bybit V5 Unified Trading
- **Indicators**: pandas, numpy (custom SuperTrend implementation)
- **Frontend**: HTML + Tailwind CSS + Vanilla JS
- **Deploy**: Render (Web Service)

## ⚡ Performance

- Procesare paralelă asincronă pentru toate simbolurile
- Request-uri API optimizate și cache pentru instruments info
- Updates la fiecare 60 secunde pentru noi lumânări 4h
- Low latency pentru execuție ordine

## 📄 Licență

MIT License - Folosire liberă

---

**⚠️ DISCLAIMER**: Acest bot este destinat exclusiv scopurilor educaționale. Trading-ul cu leverage implică risc semnificativ de pierdere. Folosește doar capital pe care ți-l permiți să îl pierzi. Nu sunt răspunzător pentru pierderi financiare.
