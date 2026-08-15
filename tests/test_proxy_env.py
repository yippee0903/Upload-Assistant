"""Tests for the proxy_url config option (src/proxy_env.py)."""

from src.proxy_env import apply_proxy_env

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
    import os

    assert os.environ["HTTP_PROXY"] == PROXY
    assert os.environ["HTTPS_PROXY"] == PROXY
    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1"


def test_custom_bypass_list(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY, "proxy_bypass": "localhost,127.0.0.1,qbit.lan"}})
    import os

    assert os.environ["NO_PROXY"] == "localhost,127.0.0.1,qbit.lan"


def test_empty_config_leaves_env_untouched(monkeypatch):
    _clear(monkeypatch)
    apply_proxy_env({"DEFAULT": {"proxy_url": ""}})
    apply_proxy_env({"DEFAULT": {}})
    apply_proxy_env({})
    import os

    for var in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY"):
        assert var not in os.environ


def test_explicit_env_vars_win(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://user-proxy:3128")
    apply_proxy_env({"DEFAULT": {"proxy_url": PROXY}})
    import os

    assert os.environ["HTTPS_PROXY"] == "http://user-proxy:3128"
    assert os.environ["HTTP_PROXY"] == PROXY
