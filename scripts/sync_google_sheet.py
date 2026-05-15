#!/usr/bin/env python3
"""
title: Sync events from Google Sheets to events.yaml
summary: |-
  Fetches multiple Google Sheets as CSVs, compares rows against
  data/events.yaml. Supports Updates, Deletions, and Additions with validation.
  Ensures strictly separate PRs by triggering individual surgical runs for each
  change.
"""

import argparse
import csv
import json
import os
import re
import sys
import urllib.request
from datetime import date
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

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
REPO_FULL_NAME = os.environ.get("GITHUB_REPOSITORY")


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
        return True
    regex = re.compile(
        r"^(?:http|ftp)s?://"
        r"(?:(?:[A-Z0-0](?:[A-Z0-0-]{0,61}[A-Z0-0])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-0-]{2,}\.?)|"
        r"localhost|"
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
        r"(?::\d+)?"
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


def find_event_index_by_title_date(
    events: list, title: str, date_val: str
) -> int:
    """
    title: Find index of event by title and date fallback.
    parameters:
      events:
        type: list
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


def trigger_surgical_sync(event_id: str) -> bool:
    """
    title: Trigger a new repository_dispatch for a specific event ID.
    parameters:
      event_id:
        type: str
    returns:
      type: bool
    """
    if not GITHUB_TOKEN or not REPO_FULL_NAME:
        print(
            "Skipping background trigger: GITHUB_TOKEN or GITHUB_REPOSITORY not set."
        )
        return False

    url = f"https://api.github.com/repos/{REPO_FULL_NAME}/dispatches"
    payload = {
        "event_type": "google_sheet_sync",
        "client_payload": {"id": str(event_id)},
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req) as response:
            return response.status in (201, 204)
    except Exception as err:
        print(f"Failed to trigger surgical sync for {event_id}: {err}")
        return False


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
    pending_ids = []

    if args.id:
        target_id = str(args.id)
        found_data = None

        for url in GOOGLE_SHEET_URLS:
            print(f"Searching for ID {target_id} in {url}...")
            try:
                req = urllib.request.Request(
                    url, headers={"User-Agent": "Mozilla/5.0"}
                )
                with urllib.request.urlopen(req) as response:
                    csv_content = response.read().decode("utf-8")
                reader = csv.DictReader(csv_content.splitlines())
                for row in reader:
                    row_id = str(row.get("id", row.get("ID", ""))).strip()
                    if row_id == target_id:
                        found_data = row
                        break
            except Exception as err:
                print(f"Error reading {url}: {err}")
            if found_data:
                break

        if not found_data:
            idx = find_event_index_by_id(events, target_id)
            if idx != -1:
                ev_to_del = events[idx]
                if "2026" in str(ev_to_del.get("date", "")):
                    print(
                        f"Deleting event {target_id} (not found in sheets)..."
                    )
                    del events[idx]
                    with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
                        yaml.dump(yaml_data, f)
                    set_github_output(
                        "BRANCH_NAME", f"sync/delete-{target_id}"
                    )
                    set_github_output("EVENT_ID", target_id)
                    set_github_output("ACTION", "delete")
                return
            else:
                print(f"Error: ID {target_id} not found anywhere.")
                return

        title = found_data.get(
            "event_name", found_data.get("Event Name", "")
        ).strip()
        date_val = found_data.get(
            "start_date", found_data.get("Start Date", "")
        ).strip()
        desc = found_data.get(
            "event_description (200 char)",
            found_data.get("Event Description", ""),
        ).strip()
        category = found_data.get(
            "event_type", found_data.get("Event Type / Category", "")
        ).strip()
        url_str = found_data.get(
            "event_url", found_data.get("Event URL", "")
        ).strip()
        location = found_data.get(
            "location", found_data.get("Location", "")
        ).strip()
        region = found_data.get("region", found_data.get("Region", "")).strip()
        tags_raw = found_data.get("tags", found_data.get("Tags", "")).strip()
        tags = (
            [t.strip() for t in tags_raw.split(",") if t.strip()]
            if tags_raw
            else []
        )

        idx = find_event_index_by_id(events, target_id)
        if idx != -1:
            ev = events[idx]
            ev["title"] = title
            ev["date"] = date_val
            ev["description"] = desc
            ev["category"] = category
            ev["url"] = url_str
            ev["location"] = location
            ev["region"] = region
            if tags:
                ev["tags"] = tags
            elif "tags" in ev:
                del ev["tags"]

            print(f"Updating event {target_id}...")
            with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
                yaml.dump(yaml_data, f)
            set_github_output("BRANCH_NAME", f"sync/update-{target_id}")
            set_github_output("EVENT_ID", target_id)
            set_github_output("ACTION", "update")
        else:
            new_event = {
                "id": target_id,
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
            print(f"Adding event {target_id}...")
            with open(EVENTS_YAML_FILE, "w", encoding="utf-8") as f:
                yaml.dump(yaml_data, f)
            set_github_output("BRANCH_NAME", f"sync/add-{target_id}")
            set_github_output("EVENT_ID", target_id)
            set_github_output("ACTION", "add")
        return

    for url in GOOGLE_SHEET_URLS:
        print(f"Scanning for changes in {url}...")
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req) as response:
                csv_content = response.read().decode("utf-8")
            reader = csv.DictReader(csv_content.splitlines())
            for row in reader:
                title = row.get(
                    "event_name", row.get("Event Name", "")
                ).strip()
                date_val = row.get(
                    "start_date", row.get("Start Date", "")
                ).strip()
                row_id = str(row.get("id", row.get("ID", ""))).strip()
                if not title or not date_val:
                    continue

                idx = find_event_index_by_id(events, row_id)
                if idx == -1:
                    final_id = row_id if row_id else get_next_id(events)
                    pending_ids.append(final_id)
                else:
                    ev_item = events[idx]
                    if (
                        ev_item.get("title") != title
                        or ev_item.get("date") != date_val
                    ):
                        pending_ids.append(row_id)

                if row_id:
                    sheet_seen_ids.add(row_id)
        except Exception as err:
            print(f"Error: {err}")

    for e_item in events:
        ev_id = str(e_item.get("id", ""))
        if (
            "2026" in str(e_item.get("date", ""))
            and ev_id not in sheet_seen_ids
        ):
            pending_ids.append(ev_id)

    pending_ids = list(dict.fromkeys(pending_ids))
    if not pending_ids:
        print("No changes detected.")
        return

    print(f"Detected {len(pending_ids)} changes. Triggering separate runs...")
    success_count = 0
    for pid in pending_ids:
        if trigger_surgical_sync(pid):
            print(f"Triggered run for event {pid}")
            success_count += 1
        else:
            print(f"Failed to trigger run for event {pid}")
    print(f"Successfully triggered {success_count} separate PR runs.")


if __name__ == "__main__":
    main()
