# ICICI Direct Breeze Connect — Setup Guide

This guide covers everything you need to connect this application to live ICICI Direct market data using the Breeze Connect API.

---

## Table of Contents

1. [Account Requirements](#1-account-requirements)
2. [Activate Breeze API Access](#2-activate-breeze-api-access)
3. [Generate API Key and Secret Key](#3-generate-api-key-and-secret-key)
4. [Static IP Requirement](#4-static-ip-requirement)
5. [IP Whitelisting Workflow](#5-ip-whitelisting-workflow)
6. [Generate a Session Token](#6-generate-a-session-token)
7. [Environment Variable Setup](#7-environment-variable-setup)
8. [Verify the Connection](#8-verify-the-connection)
9. [Daily Session Refresh](#9-daily-session-refresh)
10. [Common Authentication Issues](#10-common-authentication-issues)
11. [Switching Between Providers](#11-switching-between-providers)

---

## 1. Account Requirements

| Requirement | Details |
|---|---|
| ICICI Direct account | Active trading account with ICICI Direct |
| Account type | Individual or HUF (company accounts may have additional KYC) |
| Segment activation | Cash (NSE/BSE) must be enabled |
| API subscription | Breeze API must be subscribed — see Section 2 |
| Static IP | Required for production use — see Section 4 |

> **Note:** You do **not** need a static IP during initial development/testing. However, ICICI Direct will reject API calls from unwhitelisted IPs in production mode. For evaluation purposes, you can whitelist your dynamic IP temporarily.

---

## 2. Activate Breeze API Access

1. Log in to your ICICI Direct account at [www.icicidirect.com](https://www.icicidirect.com)
2. Navigate to **My Profile → API Subscription** (or search for "Breeze API")
3. Read and accept the API Terms & Conditions
4. Complete the API activation form — you will receive an activation confirmation by email within 1 business day
5. Once activated, proceed to the API portal at [api.icicidirect.com](https://api.icicidirect.com)

---

## 3. Generate API Key and Secret Key

1. Log in to [api.icicidirect.com](https://api.icicidirect.com) with your ICICI Direct credentials
2. Click **"Create App"** or **"My Apps"**
3. Fill in the application form:
   - **App Name**: choose any descriptive name (e.g. `market-analytics`)
   - **Redirect URL**: can be any valid URL (e.g. `https://localhost/callback`) — you do not need a live server
4. Click **Submit / Create**
5. Your credentials are now shown:
   - **API Key** → set as `ICICI_APP_KEY` (or `ICICI_API_KEY`)
   - **Secret Key** → set as `ICICI_SECRET_KEY` (or `ICICI_API_SECRET`)

> **Security:** Treat your Secret Key like a password. Never commit it to version control. Store it only in `.env` (which is git-ignored).

---

## 4. Static IP Requirement

ICICI Direct Breeze API enforces IP whitelisting in production. API calls from non-whitelisted IP addresses will be rejected with an authentication error.

| Environment | IP type needed |
|---|---|
| Local development | Dynamic IP (whitelist your current IP each session) |
| VPS / cloud server | Static IP (whitelist once, permanent) |
| CI/CD (GitHub Actions, etc.) | Runner IP changes per run — use MockProvider for CI |
| Production / 24×7 analytics | Static IP from a cloud VM (AWS/GCP/Azure) or VPN |

### Getting a static IP

The cheapest options:
- **AWS EC2 t3.micro** (~$8/month): Free Tier eligible, assign an Elastic IP
- **DigitalOcean Droplet** ($4/month): gets a persistent static IP
- **Commercial VPN with dedicated IP** (~$10/month): works without a full server

---

## 5. IP Whitelisting Workflow

1. Obtain your public IP address: `curl https://api.ipify.org` or visit [whatismyip.com](https://whatismyip.com)
2. Log in to [api.icicidirect.com](https://api.icicidirect.com)
3. Go to **My Apps → [Your App] → IP Whitelist** (or "Manage IPs")
4. Click **Add IP**, enter your static IP (e.g. `203.0.113.42`), and save
5. Whitelisting takes effect within a few minutes

> For development with a dynamic IP: repeat step 1 and 4 each time your IP changes (typically after router restart or ISP reconnect).

---

## 6. Generate a Session Token

Unlike the API key (permanent), session tokens **expire daily at midnight IST**. You need a fresh token every trading day.

### Automated method (recommended)

```bash
python scripts/refresh_session.py
```

This script:
1. Prints the login URL with your API key embedded
2. Waits for you to paste the session token
3. Writes the token to your `.env` file automatically

### Manual method

1. Construct the login URL:
   ```
   https://api.icicidirect.com/apiuser/login?api_key=YOUR_API_KEY
   ```
2. Open this URL in your browser
3. Log in with your ICICI Direct username and password
4. After login you are redirected to your app's redirect URL, which looks like:
   ```
   https://localhost/callback?apisession=abc123xyz...&status=S
   ```
5. Copy the value of the `apisession` query parameter (everything after `apisession=` and before `&`)
6. Set it in `.env`:
   ```
   ICICI_SESSION_TOKEN=abc123xyz...
   ```

> **Tip:** Bookmark the login URL for quick daily access.

---

## 7. Environment Variable Setup

Copy the example and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# ── Provider ──────────────────────────────────────────────────────────────────
# Both DATA_PROVIDER and MARKET_DATA_PROVIDER are accepted
MARKET_DATA_PROVIDER=icici

# ── ICICI Direct / Breeze Connect ─────────────────────────────────────────────
# Both ICICI_API_KEY and ICICI_APP_KEY are accepted for the API key
ICICI_APP_KEY=your_api_key_here
ICICI_SECRET_KEY=your_secret_key_here
ICICI_SESSION_TOKEN=your_daily_session_token_here

# Optional: your ICICI Direct client code / user ID (shown in diagnostics)
ICICI_CLIENT_CODE=your_client_code
```

### Accepted alias names

| Canonical name | Accepted alias | Purpose |
|---|---|---|
| `MARKET_DATA_PROVIDER` | `DATA_PROVIDER` | Provider selection |
| `ICICI_APP_KEY` | `ICICI_API_KEY` | Breeze API key |
| `ICICI_SECRET_KEY` | `ICICI_API_SECRET` | Breeze secret key |

Both names are equivalent — use whichever matches your ICICI documentation.

---

## 8. Verify the Connection

After setting credentials, run the verification script:

```bash
python scripts/verify_icici_live.py
```

Expected output when all checks pass:

```
──────────────────────────────────────────────────────────────────────
  ICICI Direct Breeze Connect — Verification Report
──────────────────────────────────────────────────────────────────────
  [PASS]      2 ms  Environment variables
              APP_KEY=...wxyz
  [PASS]     15 ms  breeze-connect package
              version 1.0.6
  [PASS]    420 ms  Authentication (generate_session)
              Session established
  [PASS]    210 ms  Health check (get_customer_details)
              Session verified by API
  [PASS]    650 ms  Historical data  (RELIANCE, last 10 days)
              5 bars | last=2024-01-05 O=2410.00 H=2465.00 L=2395.00 C=2450.00 V=1,842,310
  [PASS]    180 ms  Live quote  (RELIANCE)
              LTP=2455.50  Chg=+5.50 (+0.22%)  Bid=2455.00  Ask=2456.00  Vol=2,041,200
  [PASS]      1 ms  Corporate actions endpoint
              Returns [] as expected (Breeze does not expose this endpoint)
──────────────────────────────────────────────────────────────────────
  7/7 checks passed
  All checks passed — provider is ready for use.
──────────────────────────────────────────────────────────────────────
```

Test a specific symbol:

```bash
python scripts/verify_icici_live.py --symbol TCS
```

---

## 9. Daily Session Refresh

Session tokens expire at **midnight IST** every day. You must refresh the token before market open (09:15 IST).

### Manual refresh

```bash
python scripts/refresh_session.py
```

### Automated refresh (cron)

Add to crontab (`crontab -e`):

```cron
# Refresh ICICI session token at 08:45 IST (03:15 UTC) every weekday
15 3 * * 1-5 cd /path/to/project && python scripts/refresh_session.py --auto
```

> **Note:** The `--auto` flag is not currently implemented in `refresh_session.py` (it requires interactive input). For fully automated refresh, you would need to integrate with a headless browser or implement the OAuth flow programmatically.

### Restart after refresh

After updating the session token in `.env`, restart the pipeline to pick up the new token:

```bash
# Kill the running pipeline and restart
python run_pipeline.py --limit 500
```

---

## 10. Common Authentication Issues

### "ICICI_SESSION_TOKEN is missing"

The session token was not set in `.env`. Follow Section 6 to generate one.

### "Breeze authentication failed: 401" or "Invalid session"

The session token has expired (tokens expire at midnight IST). Run `python scripts/refresh_session.py` to get a new one.

### "Connection refused" / "Could not connect"

Your IP is not whitelisted. Log in to api.icicidirect.com and add your current IP to the whitelist (Section 5).

### "No historical data returned"

Possible causes:
- **Symbol mapping**: NSE symbols differ from Breeze stock codes (e.g. `RELIANCE` → `RELIND`). Check that the `breeze_code` column in `data/universe/nifty500.csv` is populated.
- **Market closed**: Historical data requests outside trading hours for intraday intervals may return no data. Use `interval=1day` for end-of-day data.
- **Date range**: Breeze API has data from ~2007 onwards. Very recent dates may have a 1-day lag.

### "Live quote empty outside market hours"

The `get_quotes` endpoint returns last-traded data when markets are closed, but some fields may be zeroed. This is expected. The application marks such quotes as `is_stale=True`.

### Session token format

The session token is typically a 36-character alphanumeric string. Ensure you copy only the value, without any URL encoding (e.g. `%40` should be `@`).

---

## 11. Switching Between Providers

The provider is selected by a single environment variable — no code changes needed.

### Switch to ICICI Direct (production)

```env
MARKET_DATA_PROVIDER=icici
ICICI_APP_KEY=your_key
ICICI_SECRET_KEY=your_secret
ICICI_SESSION_TOKEN=your_token
```

```bash
python run_pipeline.py --limit 500
python run_dashboard.py
```

### Switch to MockProvider (demo / offline)

```env
MARKET_DATA_PROVIDER=mock
```

```bash
python run_pipeline.py --limit 20
python run_dashboard.py
```

MockProvider requires no credentials and generates realistic synthetic data via Geometric Brownian Motion. All five dashboard pages are fully functional in mock mode.

### Startup validation

When `MARKET_DATA_PROVIDER=icici`, the application **fails fast** at startup if any credentials are missing:

```
ProviderAuthError: MARKET_DATA_PROVIDER=icici but required credentials are missing:
  - ICICI_APP_KEY (or ICICI_API_KEY)
  - ICICI_SESSION_TOKEN

Set them in your .env file. See docs/ICICI_SETUP.md for instructions.
To run without credentials: set MARKET_DATA_PROVIDER=mock
```

This prevents the pipeline from starting with incomplete configuration rather than silently degrading.

---

## Quick Reference

```bash
# Generate / renew session token
python scripts/refresh_session.py

# Verify all credentials and connectivity
python scripts/verify_icici_live.py

# Verify with a specific symbol
python scripts/verify_icici_live.py --symbol INFY

# Run pipeline with ICICI data
MARKET_DATA_PROVIDER=icici python run_pipeline.py --limit 100

# Launch dashboard (reads from DB, no provider needed)
python run_dashboard.py
```
