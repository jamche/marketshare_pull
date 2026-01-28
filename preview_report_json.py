#!/usr/bin/env python3
"""
Preview the daily report without sending email or uploading to Supabase.
Outputs JSON with the rendered HTML body and the rows that would be upserted.
"""

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from daily_passport_report import (
    COUNTRY,
    MIN_YEAR,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
    extract_listing_row,
    fetch_used_honda_passports,
    is_excluded_trim,
    parse_kilometers_value,
    render_html_table,
)


def build_supabase_rows(listings: List[Dict[str, Any]], fetched_date: str) -> List[Dict[str, Any]]:
    currency = "CAD" if COUNTRY.upper() == "CA" else "USD"
    rows: List[Dict[str, Any]] = []

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

    return rows


def main() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    listings, total_found = fetch_used_honda_passports()
    filtered_listings = [listing for listing in listings if not is_excluded_trim(listing)]

    html_table = render_html_table(filtered_listings)
    html_body = f"""
<html>
  <body>
    <p>Daily used Honda Passport report (year >= {MIN_YEAR}).</p>
    <p>Date: {today}</p>
    <p>Total listings returned: {len(filtered_listings)} (of {total_found} found)</p>
    {html_table}
    <p style="font-size: 11px; color: #666; margin-top: 16px;">
      Data source: MarketCheck Cars API.
    </p>
  </body>
</html>
"""

    supabase_rows: Optional[List[Dict[str, Any]]] = None
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        supabase_rows = build_supabase_rows(filtered_listings, today)

    payload = {
        "date": today,
        "total_found": total_found,
        "count": len(filtered_listings),
        "html_body": html_body,
        "supabase_rows": supabase_rows,
    }

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
