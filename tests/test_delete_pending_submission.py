import json
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from delete_pending_submission import main


@patch("delete_pending_submission.sys.exit")
@patch("delete_pending_submission.INPUT_FILE")
def test_main_input_file_not_found(mock_input_file, mock_exit):
    """Test main exits with code 1 if events.yaml does not exist."""
    mock_exit.side_effect = SystemExit
    mock_input_file.exists.return_value = False
    with pytest.raises(SystemExit):
        main()
    mock_exit.assert_called_with(1)


@patch("delete_pending_submission.urllib.request.urlopen")
@patch("delete_pending_submission.subprocess.run")
@patch("delete_pending_submission.INPUT_FILE")
def test_main_merged_pr_call(mock_input_file, mock_subproc, mock_urlopen, monkeypatch):
    """Test main calls delete_pending when PR is merged."""
    monkeypatch.setenv("GOOGLE_SHEET_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    monkeypatch.setenv("GOOGLE_SHEET_SECRET_TOKEN", "secret123")
    monkeypatch.setenv("PR_IS_MERGED", "true")

    mock_input_file.exists.return_value = True

    # Branch events.yaml content
    branch_yaml = "events:\n  - id: '101'\n    title: 'New Event'\n    date: '2026-10-20'\n"
    # Main events.yaml content (empty list)
    main_yaml = b"events: []"

    mock_subproc.return_value = MagicMock(stdout=main_yaml)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": True}).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open(read_data=branch_yaml)):
        main()

    # Urlopen should be called for delete_pending
    assert mock_urlopen.called
    req = mock_urlopen.call_args[0][0]
    assert "action=delete_pending" in req.full_url


@patch("delete_pending_submission.urllib.request.urlopen")
@patch("delete_pending_submission.subprocess.run")
@patch("delete_pending_submission.INPUT_FILE")
def test_main_rejected_pr_call(mock_input_file, mock_subproc, mock_urlopen, monkeypatch):
    """Test main calls both delete_pending and delete_event when PR is rejected (closed unmerged)."""
    monkeypatch.setenv("GOOGLE_SHEET_WEBAPP_URL", "https://script.google.com/macros/s/test/exec")
    monkeypatch.setenv("GOOGLE_SHEET_SECRET_TOKEN", "secret123")
    monkeypatch.setenv("PR_IS_MERGED", "false")

    mock_input_file.exists.return_value = True

    branch_yaml = "events:\n  - id: '102'\n    title: 'Rejected Event'\n    date: '2026-10-25'\n"
    main_yaml = b"events: []"

    mock_subproc.return_value = MagicMock(stdout=main_yaml)

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps({"success": True}).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_response

    with patch("builtins.open", mock_open(read_data=branch_yaml)):
        main()

    # Should have called urlopen twice (delete_pending AND delete_event)
    assert mock_urlopen.call_count == 2
    actions = [call[0][0].full_url for call in mock_urlopen.call_args_list]
    assert any("action=delete_pending" in url for url in actions)
    assert any("action=delete_event" in url for url in actions)
