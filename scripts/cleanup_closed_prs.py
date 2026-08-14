#!/usr/bin/env python3
"""
title: Cleanup closed unmerged PRs from Google Sheet.
summary: |-
  Fetches closed unmerged PRs from GitHub that were created for sync additions.
  If found, sends a delete request to the Google Sheet Web App to remove the
  event.
"""

import json
import os
import sys
import re
import urllib.parse
import urllib.request
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Any


def main() -> None:
    """
    title: Main function to clean up closed PRs.
    """
    github_token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    webapp_url = os.environ.get("GOOGLE_SHEET_WEBAPP_URL")
    secret_token = os.environ.get("GOOGLE_SHEET_SECRET_TOKEN")

    if not all([github_token, repo, webapp_url, secret_token]):
        print("Missing required environment variables.")
        sys.exit(0)

    # Fetch closed PRs
    url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=50"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitHubActions-Sync",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(req) as response:
            prs: list[dict[str, Any]] = json.loads(response.read().decode())
    except Exception as e:
        print(f"Failed to fetch PRs: {e}")
        sys.exit(1)

    parsed_url = urllib.parse.urlparse(str(webapp_url))

    def make_delete_request(title: str, date: str, event_id: str) -> None:
        """
        title: Make a delete request to the Google Sheet Web App.
        parameters:
          title:
            type: str
          date:
            type: str
          event_id:
            type: str
        """
        query_params = urllib.parse.parse_qs(parsed_url.query)
        # Type coercions to satisfy mypy
        clean_params: dict[str, list[str]] = {}
        for k, v in query_params.items():
            clean_params[str(k)] = [str(x) for x in v]

        clean_params["action"] = ["delete_event"]
        clean_params["token"] = [str(secret_token)]
        new_query = urllib.parse.urlencode(clean_params, doseq=True)

        req_url = urllib.parse.urlunparse(
            (
                str(parsed_url.scheme),
                str(parsed_url.netloc),
                str(parsed_url.path),
                str(parsed_url.params),
                new_query,
                str(parsed_url.fragment),
            )
        )

        payload = {"event_name": title, "start_date": date, "id": event_id}
        req_data = json.dumps(payload).encode("utf-8")
        delete_req = urllib.request.Request(
            str(req_url),
            data=req_data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "GitHubActions-Sync",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(delete_req) as res:
                res_body = json.loads(res.read().decode())
                print(f"Delete response for '{title}': {res_body}")
        except Exception as e:
            print(f"Failed to delete '{title}': {e}")

    now = datetime.now(timezone.utc)
    for pr in prs:
        # Check if PR is closed unmerged and is an add sync PR
        if pr.get("merged_at") is None and str(
            pr.get("head", {}).get("ref", "")
        ).startswith("sync/add-"):
            # Skip if PR was closed more than 7 days ago
            closed_at_str = pr.get("closed_at")
            if closed_at_str:
                closed_at = datetime.strptime(
                    str(closed_at_str), "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=timezone.utc)
                if (now - closed_at) > timedelta(days=7):
                    continue

            body = str(pr.get("body", ""))
            if not body:
                continue

            title_match = re.search(
                r"\-\s*\*\*Title\*\*\:\s*\`([^\`]+)\`", body
            )
            date_match = re.search(
                r"\-\s*\*\*Start Date\*\*\:\s*\`([^\`]+)\`", body
            )
            id_match = re.search(
                r"\-\s*\*\*Event ID\*\*\:\s*\`([^\`]+)\`", body
            )

            if title_match and date_match:
                title = title_match.group(1)
                date = date_match.group(1)
                event_id = id_match.group(1) if id_match else ""

                print(
                    f"Found closed unmerged PR #{pr['number']} for '{title}'. Requesting deletion..."
                )
                make_delete_request(title, date, event_id)

                # Try to delete the branch (it might already be deleted)
                branch = str(pr.get("head", {}).get("ref", ""))
                if branch:
                    try:
                        print(f"Deleting branch {branch}...")
                        subprocess.run(
                            ["git", "push", "origin", "--delete", branch],
                            capture_output=True,
                            text=True,
                        )
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
