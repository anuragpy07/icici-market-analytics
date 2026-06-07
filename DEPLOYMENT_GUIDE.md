# Deployment Guide
**ICICI Market Analytics System**  
**Repository:** https://github.com/anuragpy07/icici-market-analytics

---

## Option 1: Streamlit Community Cloud (Preferred)

**Free. Zero infrastructure. One-click from GitHub. Best for demo.**

### Prerequisites
- Repository is already pushed to GitHub ✅  
- Streamlit account: [share.streamlit.io](https://share.streamlit.io) (sign in with GitHub)

### Deploy (one-time, ~3 minutes)

1. Go to [share.streamlit.io](https://share.streamlit.io) → click **Create app**
2. Select **"Deploy a public app from GitHub"**
3. Fill in:
   | Field | Value |
   |---|---|
   | Repository | `anuragpy07/icici-market-analytics` |
   | Branch | `main` |
   | Main file path | `app/main.py` |
   | App URL | choose a short slug, e.g. `icici-analytics` |

4. Click **Advanced settings** → **Secrets** tab — paste:
   ```toml
   MARKET_DATA_PROVIDER = "mock"
   UNIVERSE_SIZE_LIMIT = "20"
   DATABASE_URL = "sqlite:///data/market_data.db"
   LOG_LEVEL = "WARNING"
   ```

5. Click **Deploy** and wait ~90 seconds for build + cold start.

### What happens on first load

The `@st.cache_resource` bootstrap in `app/main.py` detects an empty database and runs:
```
python run_pipeline.py --limit 20
```
from the repo root (absolute path, `cwd=_ROOT` is set). This populates 20 symbols in ~20 seconds. All 5 dashboard pages become fully functional immediately after.

### Switching to live ICICI data

In the Streamlit Cloud app settings → **Secrets**, update:
```toml
MARKET_DATA_PROVIDER = "icici"
ICICI_APP_KEY        = "your_breeze_api_key"
ICICI_SECRET_KEY     = "your_breeze_secret"
ICICI_SESSION_TOKEN  = "your_daily_session_token"
ICICI_CLIENT_CODE    = "your_client_code"
```
Then click **Reboot app**. The sidebar will show **🟢 ICICI — Live data**.

> **Daily refresh:** Session tokens expire at midnight IST. Update `ICICI_SESSION_TOKEN`
> in secrets and reboot each morning before market open.

### Limitations on Streamlit Community Cloud

| Limitation | Impact |
|---|---|
| Ephemeral storage | Database resets on cold start; auto-bootstrap re-populates in ~20s |
| No persistent background scheduler | Live quotes refresh on each page load, not on a background tick |
| 1 GB RAM (free tier) | `UNIVERSE_SIZE_LIMIT=20` keeps well within limits |
| App sleeps after 7 days inactivity | First load after sleep takes ~60s (cold start bootstrap) |

---

## Option 2: Render (Fallback)

**Use when you need a persistent disk and always-on deployment.**

### Step 1 — Connect repository

1. [dashboard.render.com](https://dashboard.render.com) → **New** → **Web Service**
2. Connect GitHub → select `anuragpy07/icici-market-analytics`
3. Render detects the `Dockerfile` automatically

### Step 2 — Configure

| Setting | Value |
|---|---|
| Name | `icici-market-analytics` |
| Region | Singapore (closest to India) |
| Instance type | Free |
| Docker build context | `.` |

### Step 3 — Environment variables

Add in the **Environment** tab:

```
MARKET_DATA_PROVIDER = mock
UNIVERSE_SIZE_LIMIT  = 20
DATABASE_URL         = sqlite:///data/market_data.db
LOG_LEVEL            = WARNING
```

> Render automatically injects `PORT`. The app reads it via
> `int(os.environ.get("PORT", 8501))` in `run_dashboard.py`.

### Step 4 — Deploy

Click **Create Web Service**. Build takes ~5 min. Health check passes at `/_stcore/health`.

---

## Option 3: Local / Docker

```bash
# Local (quickest)
git clone https://github.com/anuragpy07/icici-market-analytics.git
cd icici-market-analytics
pip install -r requirements.txt
python run_dashboard.py --run-pipeline --limit 20
# → http://localhost:8501

# Docker
docker build -t icici-market-analytics .
docker run -p 8501:8501 icici-market-analytics
```

---

## Streamlit Cloud — Step-by-step Screenshots Reference

```
share.streamlit.io
└── New app
    └── Deploy a public app from GitHub
        ├── Repository: anuragpy07/icici-market-analytics
        ├── Branch: main
        ├── Main file path: app/main.py   ← critical: must be this, not app/
        └── Advanced settings
            └── Secrets: [paste TOML block above]
```

---

## Environment Variables Reference

| Variable | Default | Description |
|---|---|---|
| `MARKET_DATA_PROVIDER` | `mock` | `mock` or `icici` |
| `UNIVERSE_SIZE_LIMIT` | `0` | Symbols to load (0=all; use 20 for cloud) |
| `DATABASE_URL` | `sqlite:///data/market_data.db` | SQLAlchemy URL |
| `ICICI_APP_KEY` | — | Breeze API key (also: `ICICI_API_KEY`) |
| `ICICI_SECRET_KEY` | — | Breeze secret (also: `ICICI_API_SECRET`) |
| `ICICI_SESSION_TOKEN` | — | Daily session token |
| `ICICI_CLIENT_CODE` | — | Client code (optional, for diagnostics) |
| `LOG_LEVEL` | `INFO` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `RISK_FREE_RATE` | `0.065` | Annual RFR for Sharpe (6.5%) |

---

## Verify Deployment Checklist

After deploying, confirm:

- [ ] App loads without errors in browser console
- [ ] Sidebar shows **🔵 MOCK — Demo mode** (or 🟢 if ICICI creds set)
- [ ] **Market Overview** page renders gainers/losers tables
- [ ] **Momentum Rankings** page shows top/bottom 20 with scores
- [ ] **Volatility Analysis** page shows rolling-vol chart
- [ ] **Live Monitor** page loads (market-closed message expected outside 09:15–15:30 IST)
- [ ] **Data Quality** page shows validation pass rate = 100%
- [ ] Sidebar caption shows "Last pipeline run: HH:MM:SS UTC"
