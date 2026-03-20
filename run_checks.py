"""CLI script to import a sweep JSON file into the coverage monitor.

Usage:
    python run_checks.py sweep_data.json

Posts the JSON file to http://localhost:8000/api/import/sweep
"""

import json
import sys
import urllib.request
import urllib.error


def main():
    if len(sys.argv) < 2:
        print("Usage: python run_checks.py <sweep_json_file>")
        print("  Posts the JSON file to http://localhost:8000/api/import/sweep")
        sys.exit(1)

    filepath = sys.argv[1]

    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {filepath}: {e}")
        sys.exit(1)

    url = "http://localhost:8000/api/import/sweep"
    payload = json.dumps(data).encode('utf-8')

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"Error: Could not connect to {url}: {e}")
        print("Make sure the server is running (uvicorn main:app)")
        sys.exit(1)

    summary = result.get("summary", {})
    print(f"Sweep date: {result.get('sweep_date', '?')}")
    print(f"Companies processed: {summary.get('companies_processed', 0)}")
    print(f"Indicators updated: {summary.get('indicators_updated', 0)}")
    print(f"Status changes: {summary.get('status_changes', 0)}")

    unmatched = summary.get("unmatched_indicators", [])
    if unmatched:
        print(f"\nUnmatched indicators ({len(unmatched)}):")
        for u in unmatched:
            print(f"  {u['ticker']}: {u['indicator_name']}")

    errors = summary.get("errors", [])
    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")


if __name__ == '__main__':
    main()
