#!/usr/bin/env python3
"""
title: Sync events from Google Sheets to events.yaml
summary: |-
  Fetches multiple Google Sheets as CSVs, compares rows against
  data/events.yaml,
  and appends any missing events.
"""

import csv
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVENTS_YAML_FILE = PROJECT_ROOT / "data" / "events.yaml"

# Get Google Sheet export URLs from environment (comma separated) or use default ones
GOOGLE_SHEET_URLS_ENV = os.environ.get(
    "GOOGLE_SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/10F6Z8uN7SDElBz4Z94qUhXR2i746Pijkj7iR0LPTdnk/export?format=csv&gid=93842923,https://docs.google.com/spreadsheets/d/10F6Z8uN7SDElBz4Z94qUhXR2i746Pijkj7iR0LPTdnk/export?format=csv&gid=204717323",
)
GOOGLE_SHEET_URLS = [
    url.strip() for url in GOOGLE_SHEET_URLS_ENV.split(",") if url.strip()
]


def get_next_id(events: list[dict[str, Any]]) -> str:
    """
    title: Get the next available ID.
    parameters:
      events:
        type: list[dict[str, Any]]
    returns:
      type: str
    """
    max_id = 0
    for e in events:
        try:
            curr_id = int(e.get("id", 0))
            if curr_id > max_id:
                max_id = curr_id
        except ValueError:
            pass
    return str(max_id + 1)


def is_event_exists(
    events: list[dict[str, Any]], title: str, date: str
) -> bool:
    """
    title: Check if an event already exists.
    parameters:
      events:
        type: list[dict[str, Any]]
      title:
        type: str
      date:
        type: str
    returns:
      type: bool
    """
    for e in events:
        if e.get("title") == title and str(e.get("date")) == date:
            return True
    return False


def main() -> None:
    """
    title: Main function to sync events.
    """
    if not EVENTS_YAML_FILE.exists():
        print(f"Error: {EVENTS_YAML_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    with open(EVENTS_YAML_FILE, "r", encoding="utf-8") as f:
        yaml_data = yaml.safe_load(f)

    if not yaml_data or "events" not in yaml_data:
        print("Error: Invalid events.yaml format.", file=sys.stderr)
        sys.exit(1)

    existing_events = yaml_data["events"]
    new_events_added = 0

    for url in GOOGLE_SHEET_URLS:
        print(f"Downloading CSV from: {url}")
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req) as response:
                csv_content = response.read().decode("utf-8")
        except Exception as e:
            print(
                f"Failed to fetch Google Sheet at {url}: {e}", file=sys.stderr
            )
            print(
                "Make sure the sheet sharing is set to 'Anyone with the link can view'",
                file=sys.stderr,
            )
            continue

        reader = csv.DictReader(csv_content.splitlines())

        for row in reader:
            title = row.get("event_name", "").strip()
            date = row.get("start_date", "").strip()

            if not title or not date:
                continue

            if is_event_exists(existing_events, title, date):
                continue

            new_event = {
                "id": get_next_id(existing_events),
                "title": title,
                "description": row.get(
                    "event_description (200 char)", ""
                ).strip(),
                "date": date,
                "time": "09:00",
                "location": row.get("location", "").strip(),
                "region": row.get("region", "").strip(),
                "category": row.get("event_type", "").strip(),
                "url": row.get("event_url", "").strip(),
            }

            tags_raw = row.get("tags", "").strip()
            if tags_raw:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                if tags:
                    new_event["tags"] = tags

            existing_events.append(new_event)
            new_events_added += 1
            print(f"Added new event: {title}")

    if new_events_added > 0:
        print(f"Saving {new_events_added} new events to events.yaml...")

        class Dumper(yaml.Dumper):
            def increase_indent(
                self, flow: bool = False, indentless: bool = False
            ) -> Any:
                """
                title: Custom indent
                parameters:
                  flow:
                    type: bool
                  indentless:
                    type: bool
                returns:
                  type: Any
                """
                _ = indentless
                return super(Dumper, self).increase_indent(flow, False)

        with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
            yaml.dump(
                yaml_data,
                f,
                Dumper=Dumper,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        print("Successfully updated events.yaml.")
    else:
        print("No new events found. events.yaml is up to date.")


if __name__ == "__main__":
    main()
