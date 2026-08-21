"""Contract: French trackers declare their rules as data and only report declared keys."""

import ast
import pathlib
from unittest.mock import patch

import pytest

from src.trackers.C411 import C411
from src.trackers.french.rules import FrenchRulesMixin, Rule
from src.trackers.G3MINI import G3MINI
from src.trackers.GF import GF
from src.trackers.HDF import HDF
from src.trackers.NST import NST
from src.trackers.TOS import TOS
from src.trackers.V3X import V3X

FRENCH_TRACKERS = (C411, G3MINI, GF, HDF, NST, TOS, V3X)


def _rule_keys_used(cls) -> set[str]:
    source = (pathlib.Path("src/trackers") / f"{cls.__name__}.py").read_text()
    keys = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_rule_failed" and len(node.args) >= 2:
            key = node.args[1]
            if isinstance(key, ast.Constant):
                keys.add(key.value)
    return keys


@pytest.mark.parametrize("cls", FRENCH_TRACKERS, ids=lambda c: c.__name__)
def test_rules_are_declared_unique_and_used_keys_exist(cls):
    assert issubclass(cls, FrenchRulesMixin)
    keys = [r.key for r in cls.RULES]
    assert keys and len(keys) == len(set(keys)), keys
    assert all(isinstance(r, Rule) and r.disposition in ("strict", "waivable", "advisory") for r in cls.RULES)
    undeclared = _rule_keys_used(cls) - set(keys)
    assert not undeclared, f"{cls.__name__} reports rules it does not declare: {undeclared}"


class _Fake(FrenchRulesMixin):
    tracker = "FAKE"
    RULES = (Rule("s", "strict", "x"), Rule("w", "waivable", "y", default_answer=True), Rule("a", "advisory", "z"))


def test_dispositions_drive_the_outcome():
    fake = _Fake()
    assert fake._rule_failed({}, "s", "m") is False
    assert fake._rule_failed({}, "a", "m") is True
    assert fake._rule_failed({"unattended": True}, "w", "m") is False
    with patch("src.trackers.COMMON.cli_ui.ask_yes_no", return_value=True) as ask:
        assert fake._rule_failed({"unattended": False}, "w", "m") is True
        assert ask.call_args.kwargs["default"] is True
    with pytest.raises(KeyError):
        fake._rule_failed({}, "nope", "m")
