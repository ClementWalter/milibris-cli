#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "pytest==9.1.1",
#     "click==8.5.0",
#     "curl_cffi==0.17.0",
#     "beautifulsoup4==4.15.0",
#     "lxml==6.1.3",
#     "markdownify==1.2.3",
#     "pycryptodome==4.2.0",
# ]
#
# [tool.uv]
# exclude-newer = "2026-10-27T00:00:00Z"
# ///
"""Tests for the terminal-free path: missing-session errors, the Downloads
default for files, and the headless-Chrome PDF engine. No network."""

import json
import sqlite3
import sys
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from Crypto.Cipher import AES

sys.path.insert(0, str(Path(__file__).parent.parent))
import milibris_cli  # noqa: E402


@pytest.fixture
def no_session(monkeypatch):
    """No --host, no $MILIBRIS_HOST, no config, no browser cookie."""
    monkeypatch.delenv("MILIBRIS_HOST", raising=False)
    monkeypatch.setattr(milibris_cli, "load_config", lambda: {})
    monkeypatch.setattr(milibris_cli, "browser_cookies", lambda *a, **k: [])


def test_missing_session_names_the_keychain_prompt(no_session):
    with pytest.raises(click.ClickException) as exc:
        milibris_cli.resolve_host(None)
    assert "Always Allow" in exc.value.message


def test_missing_session_names_where_to_sign_in(no_session):
    with pytest.raises(click.ClickException) as exc:
        milibris_cli.resolve_host(None)
    assert "Sign in there in Chrome" in exc.value.message


def test_missing_kiosk_cookie_names_the_kiosk(no_session):
    with pytest.raises(click.ClickException) as exc:
        milibris_cli.Kiosk("digital.example.fr")
    assert "https://digital.example.fr" in exc.value.message


def test_empty_host_env_falls_through_to_discovery(no_session, monkeypatch):
    monkeypatch.setenv("MILIBRIS_HOST", "")
    monkeypatch.setattr(milibris_cli, "discover_kiosks", lambda: [{"host": "digital.example.fr"}])
    assert milibris_cli.resolve_host(None) == "digital.example.fr"


def test_downloads_folder_is_under_home():
    assert milibris_cli.DOWNLOADS == Path.home() / "Downloads" / "milibris"


class StubIssue:
    """An issue with no pages and no articles: enough for `dump` to lay out its folder."""

    mid = "00000000-0000-0000-0000-000000000000"
    material = {"pages": []}
    metadata = {"title": "Le Canard", "publication_date": "2026-10-21"}

    def toc(self):
        return []


class StubKiosk:
    def __init__(self, host, session_key=None):
        self.host = host

    def resolve(self, ref):
        return StubIssue()


def test_dump_defaults_to_downloads_and_prints_the_absolute_path(monkeypatch, tmp_path):
    monkeypatch.setattr(milibris_cli, "Kiosk", StubKiosk)
    monkeypatch.setattr(milibris_cli, "DOWNLOADS", tmp_path)
    result = CliRunner().invoke(milibris_cli.cli, ["dump", "--host", "digital.example.fr", "--no-pdf"])
    assert result.output.strip() == str(tmp_path / "le-canard" / "2026-10-21")


@pytest.fixture
def chrome_only(monkeypatch, tmp_path):
    chrome = tmp_path / "Google Chrome"
    chrome.write_text("")
    monkeypatch.setattr(milibris_cli, "CHROME_BINARIES", (str(tmp_path / "absent"), str(chrome)))
    monkeypatch.setattr(milibris_cli.shutil, "which", lambda name: None)
    return chrome


def test_pdf_engines_uses_the_installed_chrome(chrome_only, tmp_path):
    (argv,) = milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p")
    assert argv[0] == str(chrome_only)


def test_pdf_engines_prints_to_the_absolute_out_path(chrome_only, tmp_path):
    (argv,) = milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p")
    assert f"--print-to-pdf={(tmp_path / 'out.pdf').resolve()}" in argv


def test_pdf_engines_runs_chrome_on_a_throwaway_profile(chrome_only, tmp_path):
    (argv,) = milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p")
    assert "--user-data-dir=/p" in argv


def test_pdf_engines_keeps_chrome_off_the_keychain(chrome_only, tmp_path):
    (argv,) = milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p")
    assert "--use-mock-keychain" in argv


def test_pdf_engines_tries_path_binaries_before_chrome(chrome_only, monkeypatch, tmp_path):
    monkeypatch.setattr(milibris_cli.shutil, "which", lambda name: f"/usr/local/bin/{name}")
    engines = milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p")
    assert [e[0] for e in engines] == ["wkhtmltopdf", "weasyprint", str(chrome_only)]


def test_pdf_engines_empty_without_any_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(milibris_cli, "CHROME_BINARIES", ())
    monkeypatch.setattr(milibris_cli.shutil, "which", lambda name: None)
    assert milibris_cli.pdf_engines(str(tmp_path / "doc.html"), tmp_path / "out.pdf", "/p") == []


@pytest.mark.skipif(not Path(milibris_cli.CHROME_BINARIES[0]).is_file(), reason="needs Google Chrome")
def test_html_to_pdf_prints_through_chrome(monkeypatch, tmp_path):
    monkeypatch.setattr(milibris_cli.shutil, "which", lambda name: None)
    out = tmp_path / "doc.pdf"
    milibris_cli.html_to_pdf("<html><body><h1>Été</h1></body></html>", out)
    assert out.read_bytes()[:5] == b"%PDF-"


KEY = b"0123456789abcdef"


def encrypt(value: str) -> bytes:
    """Encrypt like Chromium on macOS: `v10` + AES-CBC, PKCS7, IV of spaces."""
    data = value.encode()
    pad = 16 - len(data) % 16
    return b"v10" + AES.new(KEY, AES.MODE_CBC, iv=b" " * 16).encrypt(data + bytes([pad]) * pad)


@pytest.fixture
def cookie_store(monkeypatch, tmp_path):
    """A one-cookie Chromium store, and a keychain that records who asked."""
    con = sqlite3.connect(tmp_path / "Cookies")
    con.execute("CREATE TABLE cookies (host_key TEXT, name TEXT, encrypted_value BLOB)")
    con.execute("INSERT INTO cookies VALUES (?, ?, ?)",
                (".digital.example.fr", "exampleWebKioskSessionKey", encrypt("s%3Asession")))
    con.commit()
    con.close()
    monkeypatch.setattr(milibris_cli, "COOKIE_SOURCES",
                        [("chrome", str(tmp_path / "Cookies"), "Chrome Safe Storage")])
    asked = []
    monkeypatch.setattr(milibris_cli, "_keychain_key", lambda service: asked.append(service) or KEY)
    return asked


def test_browser_cookies_decrypts_a_kiosk_session(cookie_store):
    (row,) = milibris_cli.browser_cookies("%WebKioskSessionKey")
    assert row["value"] == "s%3Asession"


def test_browser_cookies_skips_the_keychain_without_a_match(cookie_store):
    milibris_cli.browser_cookies("%WebKioskSessionKey", "%other.fr")
    assert cookie_store == []


class StubArticleIssue(StubIssue):
    asset_url = staticmethod(lambda path: path)

    def article(self, article_id):
        return {"title": "Titre", "content": {"sections": []}}


class StubArticleKiosk(StubKiosk):
    def resolve(self, ref):
        return StubArticleIssue()


def test_read_to_a_file_with_json_reports_the_path(monkeypatch, tmp_path):
    monkeypatch.setattr(milibris_cli, "Kiosk", StubArticleKiosk)
    out = tmp_path / "a.md"
    result = CliRunner().invoke(milibris_cli.cli, ["read", "a1", "-o", str(out), "--json",
                                                   "--host", "digital.example.fr"])
    assert json.loads(result.output)["path"] == str(out)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
