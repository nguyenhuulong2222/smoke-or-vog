"""Run the voice proxy Worker's own tests (node:test) as part of the suite."""

import shutil
import subprocess
from pathlib import Path

import pytest

WORKER = Path(__file__).resolve().parent.parent / "worker" / "voice"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_worker_node_tests_pass():
    tests = sorted(str(p.relative_to(WORKER)) for p in (WORKER / "test").glob("*.test.js"))
    r = subprocess.run(["node", "--test", *tests], cwd=WORKER, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "fail 0" in r.stdout


def test_worker_config_has_no_secret():
    cfg = (WORKER / "wrangler.jsonc").read_text()
    assert "META_API_KEY" not in cfg and '"observability"' in cfg
