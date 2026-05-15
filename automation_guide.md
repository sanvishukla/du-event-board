# Google Sheets & GitHub Automation Pipeline

This document explains the automated synchronization system built to connect
Google Sheets with the `du-event-board` repository.

## Overview

The system creates a real-time, bi-directional link between a Google
Spreadsheet and the `events.yaml` registry in GitHub. It allows non-technical
editors to manage website events through a familiar spreadsheet interface while
maintaining a robust, version-controlled codebase.

## System Architecture

### 1. Data Source: Google Sheets

- **Form Responses:** Automated tab where Google Form submissions land.
- **Events Tab (`events_2026`):** The manual dashboard where editors can
  refine, edit, or delete events.

### 2. Automation Hub: Google Apps Script

- A small script attached to the Google Sheet that acts as the "brain".
- **`onFormSubmit`**: Triggers whenever a new form is filled.
- **`onEdit`**: Triggers whenever an editor manually changes a cell in the
  sheet.
- **`sendWebhookToGitHub`**: Securely notifies GitHub to start a
  synchronization run.
- **`doPost`**: A Web App endpoint that allows GitHub to "push" data back into
  the sheet.

### 3. Execution Layer: GitHub Actions

- **`sync-events.yml`**: The main workflow that runs the Python sync logic.
- **`push-to-sheets.yml`**: A helper workflow that ensures new events in the
  code are pushed back to the spreadsheet.

### 4. Logic Layer: Python Scripts

- **`scripts/sync_google_sheet.py`**: A robust script using `ruamel.yaml` that
  downloads spreadsheet data, compares it with the local YAML, and performs
  intelligent updates (Add, Edit, Delete) while preserving file formatting.
- **`scripts/push_to_sheets.py`**: A script that sends YAML data to the Google
  Apps Script Webhook.

---

## Key Features

- **Bi-directional Sync:** Changes in the Sheet create Pull Requests on GitHub;
  changes in GitHub (or missing events) are pushed back to the Sheet.
- **Full CRUD Support:** Supports Creating, Updating, and Deleting events.
- **ID Mapping:** Uses a unique `id` column to track events even if their
  titles or dates change.
- **Indentation & Comment Preservation:** Uses a round-trip YAML parser to
  ensure the `events.yaml` file remains human-readable and clean.
- **Instant Response:** Most changes reflect on the opposite platform within
  60-90 seconds.

---

## Replication & Setup Steps

To recreate this setup on a new repository or spreadsheet, follow these steps:

### Phase 1: Google Sheet Setup

1. **Create the Spreadsheet:** Ensure you have a tab named `events_2026` (or
   update the script to match your name).
2. **Add Headers:** Ensure the first row contains: `id`, `event_name`,
   `start_date`, `event_description (200 char)`, `event_type`, `event_url`,
   `location`, `region`, `tags`.
3. **Set Permissions:** Set "Anyone with the link can view" to allow the GitHub
   Action to download the CSV.

### Phase 2: Google Apps Script Setup

1. Open the sheet and go to **Extensions > Apps Script**.
2. **Copy the Script:** Paste the provided `onEdit`, `onFormSubmit`, and
   `doPost` functions.
3. **Set up Triggers:**
   - Add a trigger for `onFormSubmit` (Source: From spreadsheet, Event: On form
     submit).
   - Add a trigger for `onEdit` (Source: From spreadsheet, Event: On edit).
4. **Deploy as Web App:**
   - Click **Deploy > New Deployment > Web App**.
   - Execute as: **Me**.
   - Who has access: **Anyone**.
   - Copy the **Web App URL**.

### Phase 3: GitHub Setup

1. **Add Secrets:** Go to **Settings > Secrets and variables > Actions** and
   add:
   - `GOOGLE_SHEET_CSV_URL`: The CSV export URL for your sheet.
   - `GOOGLE_SHEET_WEBHOOK_URL`: The Web App URL from Phase 2.
   - `GH_PAT`: (Optional) A Personal Access Token if triggering from external
     accounts.

### Phase 4: Activation

1. **Initialize IDs:** If you have existing events, let the bot run once to
   assign IDs, or manually fill the `id` column with unique numbers.
2. **Test:** Edit a description in the sheet and wait for the "Update Events"
   Pull Request to appear on GitHub!

---

## Maintenance Tips

- **Formatting:** Do not change the column headers in the spreadsheet, as the
  Python script relies on them for mapping.
- **ID Integrity:** Never manually change an `id` in the spreadsheet once it
  has been assigned, as this will cause the bot to think it's a new event.
- **Trigger Errors:** If the sync stops, check the **Executions** tab in Google
  Apps Script to see if there are any webhook delivery failures.
