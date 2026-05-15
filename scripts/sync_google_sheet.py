#!/usr/bin/env python3
"""
title: Sync events from Google Sheets to events.yaml
summary: |-
  Fetches multiple Google Sheets as CSVs, compares rows against
  data/events.yaml. Supports Updates, Deletions, and Additions using
  ruamel.yaml
  to preserve comments and formatting.
"""

import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

from ruamel.yaml import YAML  # type: ignore

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
EVENTS_YAML_FILE = PROJECT_ROOT / "data" / "events.yaml"

# Get Google Sheet export URLs from environment (comma separated)
GOOGLE_SHEET_URLS_ENV = os.environ.get(
    "GOOGLE_SHEET_CSV_URL",
    "https://docs.google.com/spreadsheets/d/10F6Z8uN7SDElBz4Z94qUhXR2i746Pijkj7iR0LPTdnk/export?format=csv&gid=93842923,https://docs.google.com/spreadsheets/d/10F6Z8uN7SDElBz4Z94qUhXR2i746Pijkj7iR0LPTdnk/export?format=csv&gid=204717323",
)
GOOGLE_SHEET_URLS = [
    url.strip() for url in GOOGLE_SHEET_URLS_ENV.split(",") if url.strip()
]

WEBHOOK_URL = os.environ.get("GOOGLE_SHEET_WEBHOOK_URL", "").strip()


def get_next_id(events: list) -> str:
    """
    title: Get the next available ID.
    parameters:
      events:
        type: list
    returns:
      type: str
    """
    max_id = 0
    for ev in events:
        try:
            curr_id = int(ev.get("id", 0))
            if curr_id > max_id:
                max_id = curr_id
        except (ValueError, TypeError):
            pass
    return str(max_id + 1)


def find_event_index_by_id(events: list, event_id: str) -> int:
    """
    title: Find index of event by ID.
    parameters:
      events:
        type: list
      event_id:
        type: str
    returns:
      type: int
    """
    if not event_id:
        return -1
    for i, ev in enumerate(events):
        if str(ev.get("id")) == str(event_id):
            return i
    return -1


def find_event_index_by_title_date(events: list, title: str, date: str) -> int:
    """
    title: Find index of event by title and date fallback.
    parameters:
      events:
        type: list
      title:
        type: str
      date:
        type: str
    returns:
      type: int
    """
    for i, ev in enumerate(events):
        if (
            str(ev.get("title", "")) == title
            and str(ev.get("date", "")) == date
        ):
            return i
    return -1


def push_to_webhook(events_to_push: list) -> None:
    """
    title: Push missing events back to Google Sheets.
    parameters:
      events_to_push:
        type: list
    """
    if not WEBHOOK_URL:
        print(
            "Notice: GOOGLE_SHEET_WEBHOOK_URL not set. Cannot push missing events back to sheet."
        )
        return

    print(
        f"Pushing {len(events_to_push)} missing events back to Google Sheets..."
    )
    payload = json.dumps({"events": events_to_push}).encode("utf-8")
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
            print(f"Server response: {result}")
    except Exception as e:
        print(f"Failed to push back to Google Sheets: {e}", file=sys.stderr)


def main() -> None:
    """
    title: Main function to sync events
    """
    if not EVENTS_YAML_FILE.exists():
        print(f"Error: {EVENTS_YAML_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(EVENTS_YAML_FILE, "r", encoding="utf-8") as f:
        yaml_data = yaml.load(f)

    if not yaml_data or "events" not in yaml_data:
        print("Error: Invalid events.yaml format.", file=sys.stderr)
        sys.exit(1)

    events = yaml_data["events"]

    # We will track all IDs seen in the sheets to handle missing ones
    sheet_seen_ids = set()

    changes_made = 0

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
            continue

        reader = csv.DictReader(csv_content.splitlines())

        for row in reader:
            title = row.get("event_name", row.get("Event Name", "")).strip()
            date = row.get("start_date", row.get("Start Date", "")).strip()
            row_id = str(row.get("id", row.get("ID", ""))).strip()

            if not title or not date:
                continue

            desc = row.get(
                "event_description (200 char)",
                row.get("Event Description", ""),
            ).strip()
            category = row.get(
                "event_type", row.get("Event Type / Category", "")
            ).strip()
            url_str = row.get("event_url", row.get("Event URL", "")).strip()
            location = row.get("location", row.get("Location", "")).strip()
            region = row.get("region", row.get("Region", "")).strip()
            tags_raw = row.get("tags", row.get("Tags", "")).strip()

            tags = []
            if tags_raw:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

            # Try matching by ID first
            idx = find_event_index_by_id(events, row_id)

            # Fallback to title/date match if no ID provided in sheet
            if idx == -1 and not row_id:
                idx = find_event_index_by_title_date(events, title, date)

            if idx != -1:
                # Update existing event
                ev = events[idx]
                updated = False

                # Check fields and update if changed (only if sheet value is not empty)
                if title and ev.get("title") != title:
                    ev["title"] = title
                    updated = True
                if date and ev.get("date") != date:
                    ev["date"] = date
                    updated = True
                if desc and ev.get("description", "") != desc:
                    ev["description"] = desc
                    updated = True
                if category and ev.get("category", "") != category:
                    ev["category"] = category
                    updated = True
                if url_str and ev.get("url", "") != url_str:
                    ev["url"] = url_str
                    updated = True
                if location and ev.get("location", "") != location:
                    ev["location"] = location
                    updated = True
                if region and ev.get("region", "") != region:
                    ev["region"] = region
                    updated = True

                # Update tags if changed (only if sheet has tags)
                existing_tags = ev.get("tags", [])
                if tags and existing_tags != tags:
                    ev["tags"] = tags
                    updated = True

                if updated:
                    print(f"Updated event: {title} (ID: {ev['id']})")
                    changes_made += 1

                sheet_seen_ids.add(str(ev["id"]))

            else:
                # Create new event
                new_id = row_id if row_id else get_next_id(events)
                new_event = {
                    "id": new_id,
                    "title": title,
                    "description": desc,
                    "date": date,
                    "time": "09:00",
                    "location": location,
                    "region": region,
                    "category": category,
                    "url": url_str,
                }
                if tags:
                    new_event["tags"] = tags

                events.append(new_event)
                sheet_seen_ids.add(new_id)
                print(f"Added new event: {title} (ID: {new_id})")
                changes_made += 1

    # Find events in YAML but missing from Sheet (for 2026 events)
    missing_from_sheet = []
    for ev_item in events:
        ev_id = str(ev_item.get("id", ""))
        ev_date = str(ev_item.get("date", ""))
        # If it's a 2026 event but not seen in any of the Google Sheets
        if "2026" in ev_date and ev_id not in sheet_seen_ids:
            missing_from_sheet.append(dict(ev_item))

    if missing_from_sheet:
        push_to_webhook(missing_from_sheet)

    if changes_made > 0:
        print(f"Saving {changes_made} changes to events.yaml...")
        with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f)
        print("Successfully updated events.yaml.")
    else:
        print("No changes needed. events.yaml is up to date.")


if __name__ == "__main__":
    main()
