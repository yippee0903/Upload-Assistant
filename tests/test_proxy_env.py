"""Tests for the proxy_url config option (src/proxy_env.py)."""

import os

import pytest

from src.proxy_env import apply_proxy_env, proxy_for

PROXY = "http://127.0.0.1:3128"


def _clear(monkeypatch):
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        # setenv first so monkeypatch records the original (absent) state and
        # removes anything apply_proxy_env sets during the test at teardown
        monkeypatch.setenv(var, "sentinel")
        monkeypatch.delenv(var)


def test_sets_proxy_env_vars(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY}})

    assert os.environ["HTTP_PROXY"] == PROXY
    assert os.environ["HTTPS_PROXY"] == PROXY
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_custom_bypass_list(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY, "proxy_bypass": "localhost,127.0.0.1,qbit.lan"}})

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,qbit.lan"


def test_empty_config_leaves_env_untouched(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": ""}})
    apply_proxy_env({"DEFAULT": {}})
    apply_proxy_env({})

    for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        assert var not in os.environ


def test_explicit_env_vars_win(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://user-proxy:3128")
    monkeypatch.setenv("NO_PROXY", "myhost.lan")
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY, "proxy_bypass": "other.lan"}})

    assert os.environ["HTTPS_PROXY"] == "http://user-proxy:3128"
    assert os.environ["HTTP_PROXY"] == PROXY
    assert os.environ["NO_PROXY"] == "myhost.lan"


@pytest.mark.parametrize(
    "bad_url",
    [
        "127.0.0.1:3128",  # missing scheme
        "ftp://127.0.0.1:3128",  # unsupported scheme
        "http://",  # no host
        "http:///path",  # no host either
        "not a url",
    ],
)
def test_invalid_proxy_url_is_rejected(monkeypatch, bad_url):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": bad_url}})

    for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        assert var not in os.environ


def test_https_scheme_accepted(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": "https://proxy.lan:3128"}})

    assert os.environ["HTTPS_PROXY"] == "https://proxy.lan:3128"


def test_proxy_for_returns_proxy_for_external_host(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY}})

    assert proxy_for("https://img.example.invalid/a.png") == PROXY


def test_proxy_for_respects_no_proxy(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY, "proxy_bypass": "localhost,127.0.0.1,qbit.lan"}})

    assert proxy_for("http://qbit.lan/api") is None
    assert proxy_for("http://127.0.0.1:7476/api") is None


def test_proxy_for_without_proxy_configured(monkeypatch):
    _clear(monkeypatch)

    assert proxy_for("https://img.example.invalid/a.png") is None
