#!/usr/bin/env python3
"""
Daily Honda Passport report:
- Fetch used 2020+ Honda Passport listings via MarketCheck Cars API
- Email an HTML table of results via SMTP
"""

import os
import sys
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Load .env for local development
load_dotenv()

# ---------------------------------------------------------------------------
# Configuration – set these in your environment or .env
# ---------------------------------------------------------------------------

MARKETCHECK_API_KEY = os.environ.get("MARKETCHECK_API_KEY", "").strip()

# MarketCheck inventory search endpoint (from official docs)
MARKETCHECK_BASE_URL = "https://api.marketcheck.com/v2/search/car/active"

# Search parameters
TARGET_MAKE = "Honda"
TARGET_MODEL = "Passport"
MIN_YEAR = 2020
YEAR_LIST = os.environ.get("CAR_SEARCH_YEARS", "")  # optional comma-separated list, e.g., "2020,2021,2022"

# Optional geo filters – customize for your area or remove
COUNTRY = os.environ.get("CAR_SEARCH_COUNTRY", "CA")
ZIP_CODE = os.environ.get("CAR_SEARCH_ZIP", "")
STATE_CODE = os.environ.get("CAR_SEARCH_STATE", "")  # e.g., ON, BC, CA province/state code
RADIUS_MILES = int(os.environ.get("CAR_SEARCH_RADIUS_MILES", "100"))
# MarketCheck free plan often caps radius at 100 miles; enforce a max to avoid 422 errors.
MAX_RADIUS_ALLOWED = 100

# Supabase (optional; when set, listings will be upserted)
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_TABLE = os.environ.get("SUPABASE_TABLE", "passport_listings")

# Email configuration – works with any SMTP provider
SMTP_HOST = os.environ.get("SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASS = os.environ.get("SMTP_PASS", "").strip()

EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER)
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER)

MAX_LISTINGS = int(os.environ.get("MAX_LISTINGS", "50"))


# ---------------------------------------------------------------------------
# MarketCheck client
# ---------------------------------------------------------------------------

def fetch_used_honda_passports() -> (List[Dict[str, Any]], int):
    """
    Fetch used 2020+ Honda Passport listings from MarketCheck with basic pagination.
    """
    if not MARKETCHECK_API_KEY:
        raise RuntimeError("MARKETCHECK_API_KEY is not set in environment")

    current_year = datetime.now().year
    if YEAR_LIST:
        year_filter = YEAR_LIST
    else:
        # Build an explicit comma list (2020,2021,...) because some accounts interpret ranges as a single year.
        year_filter = ",".join(str(y) for y in range(MIN_YEAR, current_year + 1))

    base_params = {
        "api_key": MARKETCHECK_API_KEY,
        "car_type": "used",
        "make": TARGET_MAKE,
        "model": TARGET_MODEL,
        "year": year_filter,
        "sort_by": "year",  # newest first so recent model years show up
        "sort_order": "desc",
    }

    if COUNTRY:
        base_params["country"] = COUNTRY
    if STATE_CODE:
        base_params["state"] = STATE_CODE
    if ZIP_CODE:
        base_params["zip"] = ZIP_CODE
        base_params["radius"] = min(RADIUS_MILES, MAX_RADIUS_ALLOWED)

    listings: List[Dict[str, Any]] = []
    num_found: Optional[int] = None
    rows_per_page = min(MAX_LISTINGS, 50)  # stay friendly with the API defaults/limits
    start = 0

    while len(listings) < MAX_LISTINGS:
        params = dict(base_params, start=start, rows=rows_per_page)

        try:
            resp = requests.get(MARKETCHECK_BASE_URL, params=params, timeout=30)
        except requests.RequestException as exc:
            raise RuntimeError(f"Error calling MarketCheck API: {exc}") from exc

        if resp.status_code != 200:
            raise RuntimeError(f"MarketCheck API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        page_listings = data.get("listings") or data.get("results") or []
        if not isinstance(page_listings, list):
            raise RuntimeError("Unexpected API response format: 'listings' is not a list")

        if num_found is None:
            num_found = data.get("num_found") or data.get("total") or len(page_listings)

        listings.extend(page_listings)

        # Stop if we've reached the total, the requested max, or there are no more pages.
        if len(page_listings) < rows_per_page:
            break
        if num_found is not None and len(listings) >= num_found:
            break
        start += rows_per_page

    return listings[:MAX_LISTINGS], int(num_found or len(listings))


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def format_price(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return "N/A"


def format_kilometers(value: Optional[float]) -> str:
    """
    MarketCheck returns mileage in miles; convert to kilometers for Canadian users.
    """
    if value is None:
        return "N/A"
    try:
        km = float(value) * 1.60934
        return f"{int(km):,} km"
    except (TypeError, ValueError):
        return "N/A"


def extract_listing_row(listing: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a MarketCheck listing dict into a flat row for display.
    """
    build = listing.get("build", {}) or {}
    dealer = listing.get("dealer", {}) or {}

    year = listing.get("year") or build.get("year")
    price = listing.get("price") or listing.get("current_price")
    miles = listing.get("miles") or listing.get("odometer")
    trim = build.get("trim") or ""
    body_type = build.get("body_type") or ""
    exterior_color = listing.get("exterior_color") or build.get("exterior_color") or ""
    interior_color = listing.get("interior_color") or build.get("interior_color") or ""

    dealer_name = dealer.get("name") or ""
    dealer_city = dealer.get("city") or ""
    dealer_state = dealer.get("state") or ""
    dealer_phone = dealer.get("phone") or ""

    vdp_url = listing.get("vdp_url") or listing.get("deep_link") or listing.get("url") or ""

    return {
        "year": year,
        "price": format_price(price),
        "km": format_kilometers(miles),
        "trim": trim,
        "body_type": body_type,
        "ext_color": exterior_color,
        "int_color": interior_color,
        "dealer_name": dealer_name,
        "dealer_city": dealer_city,
        "dealer_state": dealer_state,
        "dealer_phone": dealer_phone,
        "vdp_url": vdp_url,
    }


def parse_kilometers_value(miles_value: Optional[float]) -> Optional[int]:
    if miles_value is None:
        return None
    try:
        km = float(miles_value) * 1.60934
        return int(km)
    except (TypeError, ValueError):
        return None


def render_html_table(listings: List[Dict[str, Any]]) -> str:
    """
    Render listings as a basic HTML table suitable for email.
    """
    if not listings:
        return "<p>No used Honda Passport listings (2020+) found for today.</p>"

    rows_html = []
    for raw in listings[:MAX_LISTINGS]:
        row = extract_listing_row(raw)
        vdp_cell = f'<a href="{row["vdp_url"]}" target="_blank">View</a>' if row["vdp_url"] else ""
        dealer_location = ", ".join(x for x in [row["dealer_city"], row["dealer_state"]] if x)

        rows_html.append(
            "<tr>"
            f"<td>{row['year'] or ''}</td>"
            f"<td>{row['price']}</td>"
            f"<td>{row['km']}</td>"
            f"<td>{row['trim'] or ''}</td>"
            f"<td>{row['body_type'] or ''}</td>"
            f"<td>{row['ext_color'] or ''}</td>"
            f"<td>{row['int_color'] or ''}</td>"
            f"<td>{row['dealer_name'] or ''}</td>"
            f"<td>{dealer_location}</td>"
            f"<td>{row['dealer_phone'] or ''}</td>"
            f"<td>{vdp_cell}</td>"
            "</tr>"
        )

    table = f"""
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse: collapse; font-family: Arial, sans-serif; font-size: 13px;">
  <thead>
    <tr style="background-color: #f0f0f0;">
      <th>Year</th>
      <th>Price</th>
      <th>KM</th>
      <th>Trim</th>
      <th>Body</th>
      <th>Exterior</th>
      <th>Interior</th>
      <th>Dealer</th>
      <th>Location</th>
      <th>Phone</th>
      <th>Link</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows_html)}
  </tbody>
</table>
"""
    return table


# ---------------------------------------------------------------------------
# Email sending
# ---------------------------------------------------------------------------

def send_email(subject: str, html_body: str) -> None:
    """
    Send an HTML email using SMTP_* environment settings.
    """
    if not all([SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_FROM, EMAIL_TO]):
        raise RuntimeError("SMTP configuration is incomplete; check environment variables.")

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject
    msg.set_content("HTML report attached. Please view this email in an HTML-capable client.")
    msg.add_alternative(html_body, subtype="html")

    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)


# ---------------------------------------------------------------------------
# Supabase ingestion
# ---------------------------------------------------------------------------

def upsert_to_supabase(listings: List[Dict[str, Any]], fetched_date: str) -> int:
    """
    Upsert listings into Supabase via PostgREST.
    Assumes a unique index on coalesce(vin, source_id), fetched_at.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return 0

    rows: List[Dict[str, Any]] = []
    currency = "CAD" if COUNTRY.upper() == "CA" else "USD"

    for raw in listings:
        row = extract_listing_row(raw)
        miles_value = raw.get("miles") or raw.get("odometer")
        km_value = parse_kilometers_value(miles_value)

        rows.append(
            {
                "vin": raw.get("vin"),
                "source_id": raw.get("id") or raw.get("listing_id"),
                "listing_url": row["vdp_url"],
                "year": row["year"],
                "price": raw.get("price") or raw.get("current_price"),
                "km": km_value,
                "trim": row["trim"],
                "body": row["body_type"],
                "exterior": row["ext_color"],
                "interior": row["int_color"],
                "dealer_name": row["dealer_name"],
                "dealer_city": row["dealer_city"],
                "dealer_state": row["dealer_state"],
                "postal": raw.get("zip") or raw.get("postal"),
                "currency": currency,
                "fetched_at": fetched_date,
            }
        )

    if not rows:
        return 0

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    resp = requests.post(
        f"{SUPABASE_URL}/rest/v1/{SUPABASE_TABLE}",
        json=rows,
        headers=headers,
        timeout=30,
    )
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"Supabase upsert failed {resp.status_code}: {resp.text[:500]}")

    return len(rows)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    today = datetime.now().strftime("%Y-%m-%d")

    try:
        listings, total_found = fetch_used_honda_passports()
    except Exception as exc:
        error_html = f"<p>Error fetching data from MarketCheck: {exc}</p>"
        try:
            send_email(subject=f"[Car Report] ERROR fetching Honda Passport data ({today})", html_body=error_html)
        except Exception as email_err:
            print(f"Failed to send error email: {email_err}", file=sys.stderr)
        return 1

    html_table = render_html_table(listings)
    count = len(listings)

    html_body = f"""
<html>
  <body>
    <p>Daily used Honda Passport report (year >= {MIN_YEAR}).</p>
    <p>Date: {today}</p>
    <p>Total listings returned: {count} (of {total_found} found)</p>
    {html_table}
    <p style="font-size: 11px; color: #666; margin-top: 16px;">
      Data source: MarketCheck Cars API.
    </p>
  </body>
</html>
"""

    # Optional: upsert to Supabase for historical trend tracking
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            ingested = upsert_to_supabase(listings, today)
            print(f"Upserted {ingested} rows to Supabase", file=sys.stderr)
        except Exception as exc:
            print(f"Failed to upsert to Supabase: {exc}", file=sys.stderr)

    try:
        send_email(subject=f"[Car Report] Used Honda Passport listings ({today})", html_body=html_body)
    except Exception as exc:
        print(f"Failed to send report email: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
