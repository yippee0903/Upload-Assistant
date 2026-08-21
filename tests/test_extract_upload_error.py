from src.cookie_auth import extract_upload_error


def test_modern_notification_body():
    html = '<div class="notification-border-e"><div class="notification-body">Torrent already exists.</div></div>'
    assert extract_upload_error(html) == "Torrent already exists."


def test_error_heading_with_sibling_paragraph():
    html = "<h2>Upload failed</h2><p>Missing NFO file</p>"
    assert extract_upload_error(html) == "Missing NFO file"


def test_legacy_single_text_node_and_no_error():
    assert extract_upload_error("<td>Error: Duplicate torrent Back</td>") == "Duplicate torrent"
    assert extract_upload_error("<html><body><p>All good</p></body></html>") == ""
