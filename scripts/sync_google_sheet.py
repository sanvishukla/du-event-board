#!/usr/bin/env python3
"""
title: Sync events from Google Sheets to events.yaml
summary: |-
  Fetches multiple Google Sheets as CSVs, compares rows against
  data/events.yaml. Supports Updates, Deletions, and Additions with validation.
  Ensures strictly separate PRs by processing one change at a time.
"""

import argparse
import csv
import os
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

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


def is_valid_url(url: str) -> bool:
    """
    title: Simple URL validation.
    parameters:
      url:
        type: str
    returns:
      type: bool
    """
    if not url:
        return True  # Optional field
    regex = re.compile(
        r"^(?:http|ftp)s?://"  # http:// or https://
        r"(?:(?:[A-Z0-0](?:[A-Z0-0-]{0,61}[A-Z0-0])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-0-]{2,}\.?)|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$",
        re.IGNORECASE,
    )
    return re.match(regex, url) is not None


def is_future_date(date_str: str) -> bool:
    """
    title: Check if date is today or in the future.
    parameters:
      date_str:
        type: str
    returns:
      type: bool
    """
    try:
        event_date = date.fromisoformat(date_str)
        return event_date >= date.today()
    except ValueError:
        return False


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
    for ev in events:
        try:
            curr_id = int(ev.get("id", 0))
            if curr_id > max_id:
                max_id = curr_id
        except (ValueError, TypeError):
            pass
    return str(max_id + 1)


def find_event_index_by_id(events: list[dict[str, Any]], event_id: str) -> int:
    """
    title: Find index of event by ID.
    parameters:
      events:
        type: list[dict[str, Any]]
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


def find_event_index_by_title_date(
    events: list[dict[str, Any]], title: str, date_val: str
) -> int:
    """
    title: Find index of event by title and date fallback.
    parameters:
      events:
        type: list[dict[str, Any]]
      title:
        type: str
      date_val:
        type: str
    returns:
      type: int
    """
    for i, ev in enumerate(events):
        if (
            str(ev.get("title", "")) == title
            and str(ev.get("date", "")) == date_val
        ):
            return i
    return -1


def set_github_output(name: str, value: str) -> None:
    """
    title: Set GitHub Actions output variable.
    parameters:
      name:
        type: str
      value:
        type: str
    """
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{name}={value}\n")


def main() -> None:
    """
    title: Main function to sync events.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", help="Only sync this specific event ID")
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
    sheet_seen_ids = set()
    changes_made = 0
    target_event_id = None
    action_type = "sync"

    for url in GOOGLE_SHEET_URLS:
        if changes_made > 0 and not args.id:
            # We already applied one change in full sync mode, stop here to ensure separate PRs
            break

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
            if changes_made > 0 and not args.id:
                break

            title = row.get("event_name", row.get("Event Name", "")).strip()
            date_val = row.get("start_date", row.get("Start Date", "")).strip()
            row_id = str(row.get("id", row.get("ID", ""))).strip()

            if not title or not date_val:
                continue

            # VALIDATION
            if not is_future_date(date_val):
                print(
                    f"Skipping '{title}': Date '{date_val}' is in the past or invalid."
                )
                continue

            url_str = row.get("event_url", row.get("Event URL", "")).strip()
            if url_str and not is_valid_url(url_str):
                print(f"Skipping '{title}': URL '{url_str}' is invalid.")
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
            location = row.get("location", row.get("Location", "")).strip()
            region = row.get("region", row.get("Region", "")).strip()
            tags_raw = row.get("tags", row.get("Tags", "")).strip()
            tags = (
                [t.strip() for t in tags_raw.split(",") if t.strip()]
                if tags_raw
                else []
            )

            idx = find_event_index_by_id(events, row_id)
            if idx == -1 and not row_id:
                idx = find_event_index_by_title_date(events, title, date_val)

            if idx != -1:
                ev = events[idx]
                updated = False
                if ev.get("title") != title:
                    ev["title"] = title
                    updated = True
                if ev.get("date") != date_val:
                    ev["date"] = date_val
                    updated = True
                if ev.get("description", "") != desc:
                    ev["description"] = desc
                    updated = True
                if ev.get("category", "") != category:
                    ev["category"] = category
                    updated = True
                if ev.get("url", "") != url_str:
                    ev["url"] = url_str
                    updated = True
                if ev.get("location", "") != location:
                    ev["location"] = location
                    updated = True
                if ev.get("region", "") != region:
                    ev["region"] = region
                    updated = True

                existing_tags = ev.get("tags", [])
                if existing_tags != tags:
                    if tags:
                        ev["tags"] = tags
                    elif "tags" in ev:
                        del ev["tags"]
                    updated = True

                if updated:
                    print(f"Updated event: {title} (ID: {ev['id']})")
                    changes_made += 1
                    target_event_id = ev["id"]
                    action_type = "update"

                sheet_seen_ids.add(str(ev["id"]))
            else:
                new_id = row_id if row_id else get_next_id(events)
                new_event = {
                    "id": new_id,
                    "title": title,
                    "description": desc,
                    "date": date_val,
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
                target_event_id = new_id
                action_type = "add"

    # Handle Deletions for 2026 events
    if not args.id and changes_made == 0:
        indices_to_delete = []
        for i, ev_item in enumerate(events):
            ev_id = str(ev_item.get("id", ""))
            ev_date = str(ev_item.get("date", ""))
            if "2026" in ev_date and ev_id not in sheet_seen_ids:
                indices_to_delete.append(i)
                print(
                    f"Detected deletion: {ev_item.get('title')} (ID: {ev_id})"
                )
                # Stop at the first deletion to ensure separate PR
                target_event_id = ev_id
                action_type = "delete"
                break

        if indices_to_delete:
            del events[indices_to_delete[0]]
            changes_made += 1

    if changes_made > 0:
        print("Saving changes to events.yaml...")
        with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
            yaml.dump(yaml_data, f)

        # Set output for GitHub Action
        branch_name = f"sync/{action_type}-{target_event_id}"
        set_github_output("BRANCH_NAME", branch_name)
        set_github_output("EVENT_ID", str(target_event_id))
        set_github_output("ACTION", action_type)
        print(f"Ready for PR on branch: {branch_name}")
    else:
        print("No changes needed.")


if __name__ == "__main__":
    main()
