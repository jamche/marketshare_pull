# Honda Passport Daily Report

Fetch daily used Honda Passport listings from the MarketCheck Cars API and email them as an HTML table via SMTP (Gmail/Outlook/Yahoo/Brevo/etc.).

## Prerequisites
- Python 3.9+.
- MarketCheck Cars API key (RapidAPI “Cars Search” free tier is fine).
- SMTP-capable email account (Gmail/Outlook/Yahoo with app password, or Brevo/SMTP2GO free plan).

## Setup
```bash
git clone https://github.com/yourname/honda_passport.git
cd honda_passport
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with your keys and preferences:
- `MARKETCHECK_API_KEY` (required)
- Geography: `CAR_SEARCH_COUNTRY` (`US` or `CA`); optional `CAR_SEARCH_STATE` (e.g., ON); optional `CAR_SEARCH_ZIP`, `CAR_SEARCH_RADIUS_MILES` (keep radius ≤ 100 on free tier to avoid 422 errors; clear `CAR_SEARCH_ZIP` if you want country/state-wide results)
- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`
- Optional: `MAX_LISTINGS` cap (default 50)
- Optional: `CAR_SEARCH_YEARS` to override year filtering with a comma list (e.g., `2020,2021,2022`). By default the script builds an explicit comma list from `MIN_YEAR` to current year to avoid range parsing quirks.
- Optional Supabase ingestion: set `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_TABLE` (default `passport_listings`) to upsert daily results for trend tracking.

## Run Once (manual)
```bash
source .venv/bin/activate
python daily_passport_report.py
```

## Run Daily on GitHub Actions (free cron)
- Add repo secrets: `MARKETCHECK_API_KEY`, `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `EMAIL_TO`.
- Optional repo variables for non-sensitive settings: `CAR_SEARCH_COUNTRY`, `CAR_SEARCH_STATE`, `CAR_SEARCH_ZIP`, `CAR_SEARCH_RADIUS_MILES`, `CAR_SEARCH_YEARS`, `MAX_LISTINGS`, `SMTP_PORT`.
- The workflow at `.github/workflows/daily-passport-report.yml` runs daily via cron (`0 15 * * *`, ~10:00 ET). You can adjust the cron string or run manually via “Run workflow” in GitHub UI.

## Behavior
- Fetches active used listings filtered to Honda Passport, year >= 2020 (adjust in script if needed).
- Builds an HTML table (year, price, kilometers, trim, body, colors, dealer info, link).
- Sends HTML email via SMTP (STARTTLS on 587 by default; SSL on 465 if configured).
- On API error: sends an error email when SMTP is configured, otherwise logs to stderr.

## Testing Tips
- Start with a small `MAX_LISTINGS` (e.g., 5) to verify email formatting.
- Temporarily set a bad `MARKETCHECK_API_KEY` to confirm the error email path.
- Check spam folder on first sends.

## Notes
- Adjust filters (price, mileage, trims, location) inside `daily_passport_report.py` as needed.
