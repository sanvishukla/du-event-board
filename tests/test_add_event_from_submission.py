import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from add_event_from_submission import (
    FIELD_MAPPING,
    clean_boolean,
    clean_tags,
    parse_date_time,
    geocode_location,
    main,
)


def test_clean_boolean():
    """Test clean_boolean helper with various truthy/falsy inputs."""
    assert clean_boolean(True) is True
    assert clean_boolean(False) is False
    assert clean_boolean("yes") is True
    assert clean_boolean("True") is True
    assert clean_boolean("1") is True
    assert clean_boolean("y") is True
    assert clean_boolean("no") is False
    assert clean_boolean("false") is False
    assert clean_boolean("0") is False
    assert clean_boolean(None) is False


def test_clean_tags():
    """Test clean_tags helper with list and string inputs."""
    assert clean_tags(None) == []
    assert clean_tags([]) == []
    assert clean_tags(["tag1", "tag2"]) == ["tag1", "tag2"]
    assert clean_tags("python, javascript, ai") == ["python", "javascript", "ai"]
    assert clean_tags("web3 blockchain") == ["web3", "blockchain"]


def test_parse_date_time_dates():
    """Test parse_date_time with standard date formats."""
    d, t = parse_date_time("2026-10-15")
    assert d == "2026-10-15"
    assert t == ""

    d, t = parse_date_time("10/15/2026")
    assert d == "2026-10-15"
    assert t == ""


def test_parse_date_time_ampm_and_seconds():
    """Test parse_date_time with 12-hour AM/PM time strings including seconds."""
    # AM times
    d, t = parse_date_time("12:00:00 AM")
    assert t == "00:00"

    d, t = parse_date_time("09:30:00 AM")
    assert t == "09:30"

    # PM times
    d, t = parse_date_time("12:00:00 PM")
    assert t == "12:00"

    d, t = parse_date_time("01:30:00 PM")
    assert t == "13:30"

    d, t = parse_date_time("11:45:00 PM")
    assert t == "23:45"


def test_parse_date_time_combined():
    """Test parse_date_time with combined date and time."""
    d, t = parse_date_time("2026-10-15 14:30:00")
    assert d == "2026-10-15"
    assert t == "14:30"


def test_field_mapping_covers_new_and_legacy_headers():
    """Verify FIELD_MAPPING maps both new Google Form questions and legacy headers."""
    # Key fields must be defined
    expected_keys = [
        "title", "date", "time", "end_date", "end_time", "category",
        "featured", "tags", "description", "organization_name", "acronym",
        "organization_url", "url_linkedin", "url_twitter", "url_other",
        "paid_or_free", "url", "image_url", "location", "city", "state-province",
        "country", "region", "language", "in_person", "virtual", "timestamp"
    ]
    for key in expected_keys:
        assert key in FIELD_MAPPING, f"Missing key '{key}' in FIELD_MAPPING"

    # Primary new column header verification
    assert "Event Name" in FIELD_MAPPING["title"]
    assert "Start Date" in FIELD_MAPPING["date"]
    assert "Start Time" in FIELD_MAPPING["time"]
    assert "End Date" in FIELD_MAPPING["end_date"]
    assert "End Time" in FIELD_MAPPING["end_time"]
    assert "Featured?" in FIELD_MAPPING["featured"]
    assert "Relevant Tags (Separated by commas)" in FIELD_MAPPING["tags"]
    assert "Event Description" in FIELD_MAPPING["description"]
    assert "Organization Name" in FIELD_MAPPING["organization_name"]
    assert "Organization Acronym" in FIELD_MAPPING["acronym"]
    assert "Official Organization Website URL" in FIELD_MAPPING["organization_url"]
    assert "LinkedIn Profile URL for Organization" in FIELD_MAPPING["url_linkedin"]
    assert "Twitter/X Profile URL for Organization" in FIELD_MAPPING["url_twitter"]
    assert "Other Social Media/Contact URL" in FIELD_MAPPING["url_other"]
    assert "Is the Event Paid or Free?" in FIELD_MAPPING["paid_or_free"]
    assert "Official Event Registration/Information URL" in FIELD_MAPPING["url"]
    assert "Event Image/Logo URL (Must be publicly accessible)" in FIELD_MAPPING["image_url"]
    assert "In-Person?" in FIELD_MAPPING["in_person"]
    assert "Virtual?" in FIELD_MAPPING["virtual"]
    assert "Location" in FIELD_MAPPING["location"]
    assert "City" in FIELD_MAPPING["city"] or "City\n" in FIELD_MAPPING["city"]
    assert "State/Province" in FIELD_MAPPING["state-province"]
    assert "Country" in FIELD_MAPPING["country"]
    assert "Region" in FIELD_MAPPING["region"]
    assert "Primary Language of the Event" in FIELD_MAPPING["language"]
    assert "Timestamp" in FIELD_MAPPING["timestamp"]


@patch("add_event_from_submission.sys.exit")
def test_main_missing_payload(mock_exit, monkeypatch):
    """Test main exits when no payload is provided."""
    mock_exit.side_effect = SystemExit
    monkeypatch.delenv("EVENT_PAYLOAD", raising=False)
    if len(sys.argv) > 1:
        sys.argv = [sys.argv[0]]

    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_with(1)


@patch("add_event_from_submission.sys.exit")
@patch("add_event_from_submission.INPUT_FILE")
def test_main_duplicate_event(mock_input_file, mock_exit, monkeypatch):
    """Test main exits gracefully when an event with same title and start date exists."""
    mock_exit.side_effect = SystemExit
    payload = json.dumps({
        "Event Name": "Existing Conference",
        "Start Date": "2026-10-15",
    })
    monkeypatch.setenv("EVENT_PAYLOAD", payload)

    mock_input_file.exists.return_value = True
    yaml_content = "events:\n  - id: '101'\n    title: 'Existing Conference'\n    date: '2026-10-15'\n"

    with patch("builtins.open", mock_open(read_data=yaml_content)):
        with pytest.raises(SystemExit):
            main()
        mock_exit.assert_called_with(0)
