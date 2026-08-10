# The common-image-host arbitration in upload.py relies on a hard-coded set of
# tracker names. Keep it in sync with the trackers that actually define
# approved_image_hosts, so a new restricted tracker is not silently skipped.

import ast
import glob
import os
import re

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _trackers_with_approved_hosts() -> set[str]:
    trackers: set[str] = set()
    for path in glob.glob(os.path.join(BASE, "src", "trackers", "*.py")):
        name = os.path.basename(path)[:-3]
        if name.startswith("_") or name in ("COMMON", "UNIT3D", "UNIT3D_TEMPLATE"):
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Attribute) and target.attr == "approved_image_hosts":
                        trackers.add(name)
    return trackers


def _hardcoded_arbitration_set() -> set[str]:
    with open(os.path.join(BASE, "upload.py"), encoding="utf-8") as f:
        source = f.read()
    match = re.search(r"trackers_with_image_host_requirements\s*=\s*\{([^}]*)\}", source)
    assert match, "trackers_with_image_host_requirements not found in upload.py"
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_arbitration_set_matches_trackers_defining_approved_hosts() -> None:
    defined = _trackers_with_approved_hosts()
    hardcoded = _hardcoded_arbitration_set()
    assert hardcoded == defined, (
        f"upload.py arbitration set out of sync: missing={sorted(defined - hardcoded)}, stale={sorted(hardcoded - defined)}"
    )
