#!/usr/bin/env python3
"""
title: Sync newly merged events to Google Sheet.
summary: |-
  Compares events from events.yaml against the Google Sheet,
  and appends any new events that do not yet exist in the sheet.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
INPUT_FILE = PROJECT_ROOT / "data" / "events.yaml"

sys.path.append(str(SCRIPT_DIR))
from sync_from_sheet import parse_date_time  # noqa: E402


def format_boolean(val: Any) -> str:
    """
    title: Convert boolean/truthy values to Yes/No, or empty if undefined.
    parameters:
      val:
        type: Any
    returns:
      type: str
    """
    if val is None or val == "":
        return ""
    if isinstance(val, bool):
        return "Yes" if val else "No"
    val_str = str(val).strip().lower()
    if val_str == "":
        return ""
    if val_str in ("true", "yes", "1", "y", "t", "x", "checked"):
        return "Yes"
    if val_str in ("false", "no", "0", "n", "f"):
        return "No"
    return str(val)


def format_featured(val: Any) -> str:
    """
    title: Format featured value as '0' or '1' for Google Sheet.
    parameters:
      val:
        type: Any
    returns:
      type: str
    """
    if val is None or val == "":
        return "0"
    if isinstance(val, bool):
        return "1" if val else "0"
    val_str = str(val).strip().lower()
    if val_str in ("true", "yes", "1", "y", "t", "x", "checked"):
        return "1"
    if val_str in ("false", "no", "0", "n", "f"):
        return "0"
    return "0"


def main() -> None:
    """
    title: Retrieve YAML events, compare with Google Sheet, and sync.
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
    get_events_url = urllib.parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            parsed_url.path,
            parsed_url.params,
            new_query,
            parsed_url.fragment,
        )
    )

    print("Fetching existing event list from Google Sheet...")
    req = urllib.request.Request(
        get_events_url, headers={"User-Agent": "GitHubActions-Sync"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_body = json.loads(response.read().decode())
            if isinstance(res_body, dict) and "error" in res_body:
                print(
                    f"Error from Google Sheet Web App: {res_body['error']}",
                    file=sys.stderr,
                )
                sys.exit(1)

            existing_keys = set()
            for s_ev in res_body:
                s_title = str(s_ev.get("event_name", "")).strip().lower()
                s_date_raw = str(s_ev.get("start_date", "")).strip()
                s_date, _ = parse_date_time(s_date_raw)

                # End date
                end_date_raw = str(s_ev.get("end_date", "")).strip()
                s_end_date = ""
                if end_date_raw:
                    s_end_date, _ = parse_date_time(end_date_raw)

                s_location = str(s_ev.get("location", "")).strip().lower()
                if s_title and s_date:
                    existing_keys.add(
                        (s_title, s_date, s_end_date, s_location)
                    )
    except Exception as e:
        print(f"Error calling Web App to fetch events: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(existing_keys)} existing events in the Google Sheet.")

    if not INPUT_FILE.exists():
        print(f"Error: {INPUT_FILE} not found.", file=sys.stderr)
        sys.exit(1)

    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {"events": []}

    events = data.get("events", [])
    print(f"Loaded {len(events)} events from events.yaml.")

    missing_events = []
    for event in events:
        title = str(event.get("title", "")).strip().lower()
        date = str(event.get("date", "")).strip()
        end_date = str(event.get("end_date", "")).strip()
        location = str(event.get("location", "")).strip().lower()
        if not title or not date:
            continue
        key = (title, date, end_date, location)
        if key not in existing_keys:
            missing_events.append(event)

    if not missing_events:
        print(
            "All events are already synced to the Google Sheet. No action needed."
        )
        sys.exit(0)

    print(f"Found {len(missing_events)} new event(s) to sync to Google Sheet.")

    parsed_post_url = urllib.parse.urlparse(webapp_url)
    post_query_params = urllib.parse.parse_qs(parsed_post_url.query)
    post_query_params["token"] = [secret_token]
    new_post_query = urllib.parse.urlencode(post_query_params, doseq=True)
    post_url = urllib.parse.urlunparse(
        (
            parsed_post_url.scheme,
            parsed_post_url.netloc,
            parsed_post_url.path,
            parsed_post_url.params,
            new_post_query,
            parsed_post_url.fragment,
        )
    )

    success_count = 0
    for event in missing_events:
        tags_val = event.get("tags", "")
        if isinstance(tags_val, list):
            tags_val = ", ".join(tags_val)

        payload = {
            "event_name": event.get("title", ""),
            "start_date": event.get("date", ""),
            "end_date": event.get("end_date", ""),
            "event_type": event.get("category", ""),
            "featured": format_featured(event.get("featured", "")),
            "tags": tags_val,
            "event_description (200 char)": event.get("description", ""),
            "organization_name": event.get("organization_name", ""),
            "organization_url": event.get("organization_url", ""),
            "url_linkedin": event.get("url_linkedin", ""),
            "url_twitter": event.get("url_twitter", ""),
            "url_other": event.get("url_other", ""),
            "acronym": event.get("acronym", ""),
            "paid_or_free": event.get("paid_or_free", ""),
            "event_url": event.get("url", ""),
            "image_url": event.get("image_url", ""),
            "location": event.get("location", ""),
            "region": event.get("region", ""),
            "in_person": format_boolean(event.get("in_person", "")),
            "virtual": format_boolean(event.get("virtual", "")),
            "language": event.get("language", ""),
        }

        print(
            f"Syncing event: '{payload['event_name']}' ({payload['start_date']})..."
        )

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            post_url,
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GitHubActions-Sync",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req) as response:
                res_body = json.loads(response.read().decode())
                if isinstance(res_body, dict) and "error" in res_body:
                    print(
                        f"Error syncing event '{payload['event_name']}': {res_body['error']}",
                        file=sys.stderr,
                    )
                else:
                    print(f"Successfully synced: '{payload['event_name']}'")
                    success_count += 1
        except Exception as e:
            print(
                f"Failed to sync event '{payload['event_name']}': {e}",
                file=sys.stderr,
            )

    print(
        f"Sync completed. Successfully synced {success_count}/{len(missing_events)} events."
    )
    if success_count < len(missing_events):
        sys.exit(1)


if __name__ == "__main__":
    main()
