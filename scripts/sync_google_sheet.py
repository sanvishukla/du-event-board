#!/usr/bin/env python3
"""
title: Sync events from Google Sheets to events.yaml
summary: |-
  Fetches multiple Google Sheets as CSVs, compares rows against
  data/events.yaml. Supports Updates, Deletions, and Additions using
  ruamel.yaml
  to preserve comments and formatting.
"""

import argparse
import csv
import os
import re
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from ruamel.yaml import YAML  # type: ignore


def validate_row(row_data: dict[str, str]) -> list[str]:
    """
    title: Validate row data from Google Sheets.
    parameters:
      row_data:
        type: dict[str, str]
    returns:
      type: list[str]
    """
    errors = []

    # Required fields check
    required = ["title", "date", "url", "category", "location", "region"]
    for field in required:
        if not row_data.get(field):
            errors.append(f"Missing required field: {field}")

    # URL format validation
    url = row_data.get("url", "")
    if url and not re.match(r"^https?://", url):
        errors.append(
            f"Invalid URL format: {url} (must start with http:// or https://)"
        )

    # Date validation (Format and Future check)
    date_str = row_data.get("date", "")
    if date_str:
        try:
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            today = datetime.now().replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            if event_date < today:
                errors.append(
                    f"Date must be in the future (or today): {date_str}"
                )
        except ValueError:
            errors.append(
                f"Invalid date format: {date_str} (expected YYYY-MM-DD)"
            )

    return errors


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


def main() -> None:
    """
    title: Main function to sync events
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Only sync this specific event ID")
    parser.add_argument(
        "--list-dirty",
        action="store_true",
        help="List IDs that need sync and exit",
    )
    args = parser.parse_args()

    if not EVENTS_YAML_FILE.exists():
        print(f"Error: {EVENTS_YAML_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(EVENTS_YAML_FILE, "r", encoding="utf-8") as f:
        yaml_data = yaml.load(f)

    if not yaml_data or "events" not in yaml_data:
        print("Error: Invalid events.yaml format.", file=sys.stderr)
        sys.exit(1)

    events = yaml_data["events"]

    # We will track all IDs seen in the sheets to handle deletions
    sheet_seen_ids = set()
    dirty_ids = set()

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

            # If a specific ID is requested, skip everything else
            if args.id and row_id != str(args.id):
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

            # Perform validation
            row_data = {
                "title": title,
                "date": date,
                "url": url_str,
                "category": category,
                "location": location,
                "region": region,
            }
            errors = validate_row(row_data)
            if errors:
                print(f"Skipping row '{title}' due to validation errors:")
                for err in errors:
                    print(f"  - {err}")
                continue

            tags = []
            if tags_raw:
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

            # Try matching by ID first
            idx = find_event_index_by_id(events, row_id)

            # Fallback to title/date match if no ID provided in sheet
            if idx == -1 and not row_id:
                idx = find_event_index_by_title_date(events, title, date)

            if idx != -1:
                ev = events[idx]
                sheet_seen_ids.add(str(ev["id"]))

                # Check if dirty
                is_dirty = False
                if ev.get("title") != title:
                    is_dirty = True
                if ev.get("date") != date:
                    is_dirty = True
                if ev.get("description", "") != desc:
                    is_dirty = True
                if ev.get("category", "") != category:
                    is_dirty = True
                if ev.get("url", "") != url_str:
                    is_dirty = True
                if ev.get("location", "") != location:
                    is_dirty = True
                if ev.get("region", "") != region:
                    is_dirty = True
                if ev.get("tags", []) != tags:
                    is_dirty = True

                if is_dirty:
                    dirty_ids.add(str(ev["id"]))

                # If a specific ID is requested, skip everything else
                if args.id and str(ev["id"]) != str(args.id):
                    continue

                if is_dirty:
                    # Update fields
                    ev["title"] = title
                    ev["date"] = date
                    ev["description"] = desc
                    ev["category"] = category
                    ev["url"] = url_str
                    ev["location"] = location
                    ev["region"] = region
                    if tags:
                        ev["tags"] = tags
                    elif "tags" in ev:
                        del ev["tags"]

                    print(
                        f"Updated event: {title} (ID: {ev['id']})",
                        file=sys.stderr,
                    )
                    changes_made += 1

            else:
                # Create new event
                # Create new event
                new_id = row_id if row_id else get_next_id(events)
                dirty_ids.add(new_id)

                if args.id and str(new_id) != str(args.id):
                    continue

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
                print(
                    f"Added new event: {title} (ID: {new_id})", file=sys.stderr
                )
                changes_made += 1

    # Handle Deletions
    for ev_item in events:
        ev_id = str(ev_item.get("id", ""))
        ev_date = str(ev_item.get("date", ""))
        if "2026" in ev_date and ev_id not in sheet_seen_ids:
            dirty_ids.add(ev_id)

    if args.list_dirty:
        # Output JSON array for GitHub Action matrix
        import json

        print(json.dumps(list(dirty_ids)))
        return

    # Deletion execution (only if no specific ID requested)
    if not args.id:
        indices_to_delete = []
        for i, ev_item in enumerate(events):
            ev_id = str(ev_item.get("id", ""))
            ev_date = str(ev_item.get("date", ""))
            if "2026" in ev_date and ev_id not in sheet_seen_ids:
                indices_to_delete.append(i)
                print(
                    f"Deleted event: {ev_item.get('title')} (ID: {ev_id})",
                    file=sys.stderr,
                )

        for i in sorted(indices_to_delete, reverse=True):
            del events[i]
            changes_made += 1
    elif args.id:
        # Special case: Deletion of a specific ID
        # If the ID was dirty but wasn't found in the sheet loop above, it must be a deletion
        if args.id not in sheet_seen_ids:
            idx = find_event_index_by_id(events, args.id)
            if idx != -1:
                print(f"Deleting event ID: {args.id}", file=sys.stderr)
                del events[idx]
                changes_made += 1

    if changes_made > 0:
        print(f"Saving {changes_made} changes to events.yaml...")
        with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f)
        print("Successfully updated events.yaml.")
    else:
        print("No changes needed. events.yaml is up to date.")


if __name__ == "__main__":
    main()
