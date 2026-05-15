#!/usr/bin/env python3
"""
title: Push events.yaml to Google Sheets Webhook
summary: |-
  Reads the current data/events.yaml file and sends it as a JSON payload
  to a configured Google Apps Script Web App URL. The Google Apps Script
  will then process the events and update the 2026 sheet.
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVENTS_YAML_FILE = PROJECT_ROOT / "data" / "events.yaml"

WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL", "").strip()


def main() -> None:
    """
    title: Main function to push events to Google Sheets.
    """
    if not WEBHOOK_URL:
        print(
            "Notice: GOOGLE_SHEET_WEBHOOK_URL is not set. Skipping push to sheets."
        )
        sys.exit(0)

    if not EVENTS_YAML_FILE.exists():
        print(f"Error: {EVENTS_YAML_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Reading events from {EVENTS_YAML_FILE}...")
    with open(EVENTS_YAML_FILE, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)

    if not yaml_data or "events" not in yaml_data:
        print("Error: Invalid events.yaml format.", file=sys.stderr)
        sys.exit(1)

    events = yaml_data["events"]
    print(f"Found {len(events)} events. Preparing to send to Google Sheets...")

    payload = json.dumps({"events": events}).encode("utf-8")

    req = urllib.request.Request(
        WEBHOOK_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            result = response.read().decode("utf-8")
            print(
                f"Successfully pushed to Google Sheets! Server response: {result}"
            )
    except Exception as e:
        print(f"Failed to push to Google Sheets: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
