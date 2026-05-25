#!/usr/bin/env python3
"""
title: Sync newly merged events to Google Sheet.
summary: |-
  Compares events from events.yaml against the Google Sheet,
  and appends any new events that do not yet exist in the sheet.
"""

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


def format_boolean(val: Any) -> str:
    """
    title: Convert boolean/truthy values to Yes/No.
    parameters:
      val:
        type: Any
    returns:
      type: str
    """
    if isinstance(val, bool):
        return "Yes" if val else "No"
    val_str = str(val).strip().lower()
    if val_str in ("true", "yes", "1", "y", "t", "x", "checked"):
        return "Yes"
    if val_str in ("false", "no", "0", "n", "f", ""):
        return "No"
    return str(val)


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
    query_params["action"] = ["get_events"]
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
            existing_keys = set(res_body)
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
        title = str(event.get("title", "")).strip()
        date = str(event.get("date", "")).strip()
        if not title or not date:
            continue
        key = f"{title}|{date}"
        if key not in existing_keys:
            missing_events.append(event)

    if not missing_events:
        print(
            "All events are already synced to the Google Sheet. No action needed."
        )
        sys.exit(0)

    print(f"Found {len(missing_events)} new event(s) to sync to Google Sheet.")

    post_url = webapp_url
    if "token" not in query_params:
        parsed_url = urllib.parse.urlparse(webapp_url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        query_params["token"] = [secret_token]
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        post_url = urllib.parse.urlunparse(
            (
                parsed_url.scheme,
                parsed_url.netloc,
                parsed_url.path,
                parsed_url.params,
                new_query,
                parsed_url.fragment,
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
            "featured": format_boolean(event.get("featured", "")),
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
