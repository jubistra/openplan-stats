#!/usr/bin/env python3
"""Fetch Cloudflare zone analytics via GraphQL and write stats/stats.json.
Requires env vars: CF_API_TOKEN, ZONE_ID.
Never prints or logs the token.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

CF_API_TOKEN = os.environ.get("CF_API_TOKEN")
ZONE_ID = os.environ.get("ZONE_ID")

if not CF_API_TOKEN or not ZONE_ID:
    print("Missing CF_API_TOKEN or ZONE_ID env vars", file=sys.stderr)
    sys.exit(1)

today = datetime.now(timezone.utc).date()
start = today - timedelta(days=29)

query = """
query ($zoneTag: String!, $since: Date!, $until: Date!) {
  viewer {
    zones(filter: {zoneTag: $zoneTag}) {
      httpRequests1dGroups(
        limit: 30
        filter: {date_geq: $since, date_leq: $until}
        orderBy: [date_ASC]
      ) {
        dimensions { date }
        sum { requests pageViews bytes threats cachedRequests }
        uniq { uniques }
      }
    }
  }
}
"""

payload = json.dumps({
    "query": query,
    "variables": {
        "zoneTag": ZONE_ID,
        "since": start.isoformat(),
        "until": today.isoformat(),
    },
}).encode("utf-8")

req = urllib.request.Request(
    "https://api.cloudflare.com/client/v4/graphql",
    data=payload,
    method="POST",
    headers={
        "Authorization": f"Bearer {CF_API_TOKEN}",
        "Content-Type": "application/json",
    },
)

try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    print(f"HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')}", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Request failed: {e}", file=sys.stderr)
    sys.exit(1)

if result.get("errors"):
    print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
    sys.exit(1)

zones = result.get("data", {}).get("viewer", {}).get("zones", [])
groups = zones[0].get("httpRequests1dGroups", []) if zones else []

days = []
totals = {"requests": 0, "pageViews": 0, "uniques": 0, "threats": 0, "bytes": 0}

for g in groups:
    date = g["dimensions"]["date"]
    s = g["sum"]
    u = g["uniq"]["uniques"]
    days.append({
        "date": date,
        "requests": s["requests"],
        "pageViews": s["pageViews"],
        "uniques": u,
        "threats": s["threats"],
        "bytes": s["bytes"],
    })
    totals["requests"] += s["requests"]
    totals["pageViews"] += s["pageViews"]
    totals["uniques"] += u
    totals["threats"] += s["threats"]
    totals["bytes"] += s["bytes"]

output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "zone": "openplaninteriordevelopment.co.uk",
    "range_days": 30,
    "totals": totals,
    "days": days,
}

out_path = os.path.join(os.path.dirname(__file__), "stats.json")
with open(out_path, "w") as f:
    json.dump(output, f, indent=2)

print(f"Wrote {out_path} with {len(days)} days of data")
