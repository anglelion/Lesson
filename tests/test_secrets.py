from backend.app.checks.secrets import secret_check


def test_secret_value_is_redacted(tmp_path):
    (tmp_path / "config.py").write_text(
        "api_key='ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890'", encoding="utf-8"
    )
    findings = secret_check(str(tmp_path))
    assert findings
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in findings[0]["evidence"]
