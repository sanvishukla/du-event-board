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
    new_events_list = []

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
            # Support both snake_case (2026 sheet) and Title Case (Form Responses)
            title = row.get("event_name", row.get("Event Name", "")).strip()
            date = row.get("start_date", row.get("Start Date", "")).strip()

            if not title or not date:
                continue

            if is_event_exists(existing_events, title, date):
                continue

            desc = row.get(
                "event_description (200 char)",
                row.get("Event Description", ""),
            ).strip()
            category = row.get(
                "event_type", row.get("Event Type / Category", "")
            ).strip()
            url_str = row.get("event_url", row.get("Event URL", "")).strip()

            # Location, Region, Tags are usually the same or just Capitalized
            location = row.get("location", row.get("Location", "")).strip()
            region = row.get("region", row.get("Region", "")).strip()
            tags_raw = row.get("tags", row.get("Tags", "")).strip()

            new_event = {
                "id": get_next_id(existing_events),
                "title": title,
                "description": desc,
                "date": date,
                "time": "09:00",
                "location": location,
                "region": region,
                "category": category,
                "url": url_str,
            }

            if tags_raw:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                if tags:
                    new_event["tags"] = tags

            new_events_list.append(new_event)
            existing_events.append(new_event)
            new_events_added += 1
            print(f"Added new event: {title}")

    if new_events_added > 0:
        print(f"Appending {new_events_added} new events to events.yaml...")
        with open(EVENTS_YAML_FILE, "a", encoding="utf-8") as f:
            for ev in new_events_list:
                f.write("\n")
                f.write(f'  - id: "{ev["id"]}"\n')
                f.write(f'    title: "{ev["title"]}"\n')
                if ev.get("description"):
                    # Handle multiline descriptions safely by escaping quotes
                    desc = ev["description"].replace('"', '\\"')
                    f.write(f'    description: "{desc}"\n')
                f.write(f'    date: "{ev["date"]}"\n')
                f.write(f'    time: "{ev["time"]}"\n')
                if ev.get("location"):
                    f.write(f'    location: "{ev["location"]}"\n')
                if ev.get("region"):
                    f.write(f'    region: "{ev["region"]}"\n')
                if ev.get("category"):
                    f.write(f'    category: "{ev["category"]}"\n')
                if ev.get("url"):
                    f.write(f'    url: "{ev["url"]}"\n')
                if ev.get("tags"):
                    f.write("    tags:\n")
                    for tag in ev["tags"]:
                        f.write(f"      - {tag}\n")
        print("Successfully appended to events.yaml.")
    else:
        print("No new events found. events.yaml is up to date.")


if __name__ == "__main__":
    main()
