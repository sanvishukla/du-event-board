#!/usr/bin/env python3
"""
title: Sync events from Google Sheet to repository.
summary: |-
  Fetches all events from the Google Sheet, compares them to events.yaml,
  detects edits and additions, geocodes coordinates, and updates events.yaml.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_ROOT / "data" / "events.yaml"
CACHE_FILE = PROJECT_ROOT / "data" / ".geocode_cache.json"

FIELD_MAPPING = {
    "title": ["event_name", "title", "event name"],
    "end_date": ["end_date", "end date"],
    "category": ["event_type", "category", "event type"],
    "description": [
        "event_description (200 char)",
        "event_description",
        "description",
        "event description",
    ],
    "organization_name": [
        "organization_name",
        "organization name",
        "hosting organization name",
    ],
    "acronym": ["acronym", "organization acronym"],
    "organization_url": [
        "organization_url",
        "organization url",
        "official organization website url",
    ],
    "url_linkedin": ["url_linkedin", "linkedin profile url"],
    "url_twitter": ["url_twitter", "twitter/x profile url", "twitter url"],
    "url_other": [
        "url_other",
        "other social media/contact url",
        "other social url",
    ],
    "paid_or_free": [
        "paid_or_free",
        "paid or free",
        "is the event paid or free?",
    ],
    "url": [
        "event_url",
        "url",
        "official event registration/information url",
    ],
    "image_url": ["image_url", "event image/logo url", "image url"],
    "location": ["location", "physical location"],
    "region": ["region", "geographic region"],
    "language": ["language", "primary language"],
}


def get_field_value(s_ev: dict[str, Any], key: str) -> str:
    """
    title: Retrieve event field value from spreadsheet event object.
    parameters:
      s_ev:
        type: dict[str, Any]
      key:
        type: str
    returns:
      type: str
    """
    candidates = FIELD_MAPPING.get(key, [key])
    s_ev_normalized = {k.strip().lower(): v for k, v in s_ev.items()}

    for candidate in candidates:
        cand_norm = candidate.strip().lower()
        if cand_norm in s_ev_normalized:
            return str(s_ev_normalized[cand_norm]).strip()
    return ""


def clean_boolean(val: Any) -> bool:
    """
    title: Normalize any truthy value to a boolean.
    parameters:
      val:
        type: Any
    returns:
      type: bool
    """
    if isinstance(val, bool):
        return val
    val_str = str(val).strip().lower()
    return any(
        keyword in val_str
        for keyword in ("true", "yes", "1", "y", "t", "x", "checked")
    )


def clean_tags(val: Any) -> list[str]:
    """
    title: Clean and split tag values into a list of strings.
    parameters:
      val:
        type: Any
    returns:
      type: list[str]
    """
    if not val:
        return []
    if isinstance(val, list):
        return [str(t).strip() for t in val if t]
    return [t.strip() for t in str(val).replace(",", " ").split() if t.strip()]


def parse_date_time(dt_str: str) -> tuple[str, str]:
    """
    title: Parse date and time from various formats.
    parameters:
      dt_str:
        type: str
    returns:
      type: tuple[str, str]
    """
    dt_str = dt_str.strip()
    if not dt_str:
        return "", ""

    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(dt_str, fmt)
            time_val = (
                dt.strftime("%H:%M") if "H" in fmt or "M" in fmt else "12:00"
            )
            return dt.strftime("%Y-%m-%d"), time_val
        except ValueError:
            continue

    # Fallback regex parsing
    date_match = re.search(
        r"(\d{4}[-/]\d{2}[-/]\d{2})|(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})", dt_str
    )
    time_match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)", dt_str)

    date_val = ""
    time_val = "12:00"

    if date_match:
        raw_date = date_match.group(0).replace("/", "-")
        for fmt in [
            "%Y-%m-%d",
            "%m-%d-%Y",
            "%d-%m-%Y",
            "%m-%d-%y",
            "%d-%m-%y",
        ]:
            try:
                dt = datetime.strptime(raw_date, fmt)
                date_val = dt.strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
    if time_match:
        time_val = time_match.group(0)
        parts = time_val.split(":")
        time_val = f"{int(parts[0]):02d}:{int(parts[1]):02d}"

    return date_val, time_val


def get_cache() -> dict[str, Any]:
    """
    title: Retrieve geocoding cache.
    returns:
      type: dict[str, Any]
    """
    if CACHE_FILE.exists():
        try:
            with open(CACHE_FILE, "r") as f:
                res: dict[str, Any] = json.load(f)
                return res
        except Exception:
            return {}
    return {}


def save_cache(cache: dict[str, Any]) -> None:
    """
    title: Save geocoding cache back to disk.
    parameters:
      cache:
        type: dict[str, Any]
    """
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save geocode cache: {e}")


def geocode_location(location_str: str) -> tuple[float, float] | None:
    """
    title: Resolve location string into coordinates.
    parameters:
      location_str:
        type: str
    returns:
      type: tuple[float, float] | None
    """
    if not location_str or location_str.lower() == "online":
        return None

    cache = get_cache()
    if location_str in cache:
        return (cache[location_str][0], cache[location_str][1])

    print(f"Fetching coordinates for '{location_str}'...")
    query = urllib.parse.quote(location_str)
    url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&limit=1"

    req = urllib.request.Request(
        url, headers={"User-Agent": "DU-Event-Board-App/1.0"}
    )
    try:
        time.sleep(1.1)
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data and len(data) > 0:
                coords = (float(data[0]["lat"]), float(data[0]["lon"]))
                cache[location_str] = coords
                save_cache(cache)
                return coords
    except Exception as e:
        print(
            f"Warning: Geocoding failed for '{location_str}': {e}",
            file=sys.stderr,
        )
    return None


def format_yaml_field(key: str, val: Any, indent: int = 4) -> str:
    """
    title: Format a key-value pair to YAML format.
    parameters:
      key:
        type: str
      val:
        type: Any
      indent:
        type: int
    returns:
      type: str
    """
    dumped = yaml.safe_dump(
        {key: val}, default_flow_style=False, allow_unicode=True
    ).strip()
    lines = dumped.splitlines()
    formatted_lines = []
    for line in lines:
        if line.startswith("- "):
            formatted_lines.append(" " * (indent + 2) + line)
        else:
            formatted_lines.append(" " * indent + line)
    return "\n".join(formatted_lines)


def split_yaml_into_blocks(file_path: Path) -> tuple[str, dict[str, str]]:
    """
    title: Split events.yaml into header and individual event blocks.
    parameters:
      file_path:
        type: Path
    returns:
      type: tuple[str, dict[str, str]]
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    lines = content.splitlines(keepends=True)
    header_lines = []
    blocks = {}

    current_id = None
    current_block_lines = []

    for line in lines:
        stripped = line.strip()
        match = re.match(r"^\s*-\s+id:\s*['\"]?(\d+)['\"]?$", stripped)
        if match:
            if current_id is not None:
                blocks[current_id] = "".join(current_block_lines)
            current_id = match.group(1)
            current_block_lines = [line]
        else:
            if current_id is None:
                header_lines.append(line)
            else:
                current_block_lines.append(line)

    if current_id is not None:
        blocks[current_id] = "".join(current_block_lines)

    header = "".join(header_lines)
    return header, blocks


def format_event_as_yaml(ev: dict[str, Any]) -> str:
    """
    title: Format an event dictionary to standard YAML layout.
    parameters:
      ev:
        type: dict[str, Any]
    returns:
      type: str
    """
    key_order = [
        "id",
        "lat",
        "lng",
        "title",
        "description",
        "date",
        "time",
        "location",
        "region",
        "category",
        "url",
        "tags",
        "end_date",
        "featured",
        "organization_name",
        "organization_url",
        "url_linkedin",
        "url_twitter",
        "url_other",
        "acronym",
        "paid_or_free",
        "image_url",
        "in_person",
        "virtual",
        "language",
    ]

    lines = []
    lines.append(f'  - id: "{ev.get("id")}"')

    for k in key_order[1:]:
        val = ev.get(k)
        if val == "" or val is None or val == [] or val is False:
            if k not in [
                "title",
                "description",
                "date",
                "time",
                "location",
                "region",
                "category",
            ]:
                continue

        if k == "tags" and isinstance(val, list):
            lines.append("    tags:")
            for tag in val:
                lines.append(f"      - {tag}")
        elif isinstance(val, bool):
            lines.append(f"    {k}: {str(val).lower()}")
        elif isinstance(val, (int, float)):
            lines.append(f"    {k}: {val}")
        else:
            val_str = str(val).replace('"', '\\"')
            lines.append(f'    {k}: "{val_str}"')

    return "\n".join(lines) + "\n"


def main() -> None:
    """
    title: >-
      Retrieve sheet events, detect additions/edits, and write events.yaml.
    """
    webapp_url = os.environ.get("GOOGLE_SHEET_WEBAPP_URL")
    secret_token = os.environ.get("GOOGLE_SHEET_SECRET_TOKEN")

    if not webapp_url or not secret_token:
        print(
            "Error: GOOGLE_SHEET_WEBAPP_URL and GOOGLE_SHEET_SECRET_TOKEN environment variables are required.",
            file=sys.stderr,
        )
        sys.exit(1)

    parsed_url = urllib.parse.urlparse(webapp_url)
    query_params = urllib.parse.parse_qs(parsed_url.query)
    query_params["action"] = ["get_sheet_events"]
    query_params["token"] = [secret_token]
    new_query = urllib.parse.urlencode(query_params, doseq=True)
    get_sheet_events_url = urllib.parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment,
        )
    )

    print("Fetching all events from Google Sheet...")
    req = urllib.request.Request(
        get_sheet_events_url, headers={"User-Agent": "GitHubActions-Sync"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            sheet_events = json.loads(response.read().decode())
            if isinstance(sheet_events, dict) and "error" in sheet_events:
                print(
                    f"Error from Google Sheet Web App: {sheet_events['error']}",
                    file=sys.stderr,
                )
                sys.exit(1)
    except Exception as e:
        print(
            f"Error calling Web App to fetch sheet events: {e}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Successfully loaded {len(sheet_events)} events from Google Sheet.")

    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        current_data = yaml.safe_load(f) or {"events": []}

    yaml_events = current_data.get("events", [])
    print(f"Loaded {len(yaml_events)} existing events from events.yaml.")

    # Guard against empty sheet fetch to prevent wiping database
    if not sheet_events:
        print(
            "Warning: Google Sheet returned 0 events. Aborting to prevent wiping the database."
        )
        sys.exit(0)

    # Index yaml events by (title.lower, date, end_date, location.lower) for lookup
    yaml_index = {}
    for ev in yaml_events:
        t = str(ev.get("title", "")).strip().lower()
        d = str(ev.get("date", "")).strip()
        ed = str(ev.get("end_date", "")).strip()
        loc = str(ev.get("location", "")).strip().lower()
        yaml_index[(t, d, ed, loc)] = ev

    # We will build a list of updated events, keeping the order of IDs
    updated_yaml_events: list[dict[str, Any]] = []

    # Track existing IDs to calculate next ID
    max_id = 0
    for ev in yaml_events:
        try:
            eid = int(ev.get("id", 0))
            if eid > max_id:
                max_id = eid
        except ValueError:
            pass

    has_changes = False
    processed_yaml_ids = set()

    # Process events from Sheet
    for s_ev in sheet_events:
        s_title = get_field_value(s_ev, "title")
        s_date_raw = get_field_value(s_ev, "date")
        if not s_title or not s_date_raw:
            continue

        s_date, s_time = parse_date_time(s_date_raw)

        # End date
        end_date_raw = get_field_value(s_ev, "end_date")
        s_end_date = ""
        if end_date_raw:
            s_end_date, _ = parse_date_time(end_date_raw)

        # Normalization of virtual/location
        virtual_val = clean_boolean(get_field_value(s_ev, "virtual"))
        s_location = get_field_value(s_ev, "location")
        if not s_location:
            s_location = "Online" if virtual_val else "TBD"

        key = (s_title.lower(), s_date, s_end_date, s_location.lower())

        # Build normalized representation
        mapped_event: dict[str, Any] = {}
        for target_key in FIELD_MAPPING.keys():
            mapped_event[target_key] = get_field_value(s_ev, target_key)

        mapped_event["title"] = s_title
        mapped_event["date"] = s_date
        mapped_event["time"] = s_time if s_time else "12:00"
        mapped_event["end_date"] = s_end_date
        mapped_event["location"] = s_location

        # Normalize tags
        mapped_event["tags"] = clean_tags(get_field_value(s_ev, "tags"))

        # Normalize booleans
        mapped_event["featured"] = clean_boolean(
            get_field_value(s_ev, "featured")
        )
        mapped_event["in_person"] = clean_boolean(
            get_field_value(s_ev, "in_person")
        )
        mapped_event["virtual"] = virtual_val

        # Standardize paid_or_free
        paid_or_free_val = get_field_value(s_ev, "paid_or_free").lower()
        if "free" in paid_or_free_val:
            mapped_event["paid_or_free"] = "free"
        elif "paid" in paid_or_free_val:
            mapped_event["paid_or_free"] = "paid"
        else:
            mapped_event["paid_or_free"] = ""

        # Safe required TBD placeholders to prevent validation failure
        if not mapped_event.get("description"):
            mapped_event["description"] = "TBD"
        if not mapped_event.get("region"):
            mapped_event["region"] = "Online" if virtual_val else "TBD"
        if not mapped_event.get("category"):
            mapped_event["category"] = "TBD"

        # Look up in index
        if key in yaml_index:
            existing_ev = yaml_index[key]
            processed_yaml_ids.add(str(existing_ev.get("id")))

            # Check if any field changed
            ev_changed = False
            for k, val in mapped_event.items():
                if existing_ev.get(k) != val:
                    ev_changed = True
                    break

            if ev_changed:
                print(f"Edit detected for event: '{s_title}' on {s_date}")
                has_changes = True
                mapped_event["id"] = existing_ev.get("id")
                # Location is part of the key and identical, so coordinates can be preserved
                mapped_event["lat"] = existing_ev.get("lat", "")
                mapped_event["lng"] = existing_ev.get("lng", "")

                updated_yaml_events.append(mapped_event)
            else:
                # Keep existing unmodified event
                updated_yaml_events.append(existing_ev)
        else:
            # Addition detected
            print(f"New event detected: '{s_title}' on {s_date}")
            has_changes = True
            max_id += 1
            mapped_event["id"] = str(max_id)

            coords = geocode_location(str(mapped_event["location"]))
            mapped_event["lat"] = coords[0] if coords else ""
            mapped_event["lng"] = coords[1] if coords else ""

            updated_yaml_events.append(mapped_event)

    # Keep events from YAML that were not matched by any sheet event.
    # They will be synced back to the sheet on merge.
    for ev in yaml_events:
        event_id = str(ev.get("id", ""))
        if event_id not in processed_yaml_ids:
            print(
                f"Event in YAML but not in Google Sheet (keeping in database): '{ev.get('title')}' on {ev.get('date')}"
            )
            updated_yaml_events.append(ev)

    if not has_changes:
        print(
            "No additions, edits, or deletions detected. Workspace is in sync with Google Sheet."
        )
        sys.exit(0)

    # Sort events by ID (as integers) to keep order consistent
    try:
        updated_yaml_events.sort(key=lambda x: int(x.get("id", 0)))
    except Exception:
        pass

    # Load original blocks to preserve formatting and quotes for unmodified events
    header, blocks = split_yaml_into_blocks(INPUT_FILE)

    yaml_blocks = []
    for ev in updated_yaml_events:
        event_id = str(ev.get("id", ""))

        # Check if this event was modified compared to the original parsed events
        original_ev = next(
            (x for x in yaml_events if str(x.get("id")) == event_id), None
        )

        is_modified = True
        if original_ev is not None:
            is_modified = False
            for k in set(list(ev.keys()) + list(original_ev.keys())):
                if ev.get(k) != original_ev.get(k):
                    is_modified = True
                    break

        if not is_modified and event_id in blocks:
            yaml_blocks.append(blocks[event_id])
        else:
            yaml_blocks.append(format_event_as_yaml(ev) + "\n")

    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        final_header = header
        if final_header and not final_header.endswith("\n"):
            final_header += "\n"
        f.write(final_header + "".join(yaml_blocks))

    print("Successfully updated events.yaml")

    # Re-generate src/data/events.json
    print("Re-generating events.json...")
    try:
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(PROJECT_ROOT / "scripts" / "generate_events_json.py"),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"Error running generate_events_json.py: {e}", file=sys.stderr)
        print(e.stderr, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
