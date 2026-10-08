"""Gemeinsame Lesezeichen: führt den Node-Test für dienst/lesezeichen.js aus.

Übersprungen, wenn Node fehlt oder zu alt ist (node:sqlite braucht Node 22.5+)."""
import os
import shutil
import subprocess

import pytest

HIER = os.path.dirname(os.path.abspath(__file__))


def _node_ok():
    node = shutil.which("node")
    if not node:
        return None
    r = subprocess.run([node, "-e", "require('node:sqlite')"], capture_output=True)
    return node if r.returncode == 0 else None


@pytest.mark.skipif(_node_ok() is None, reason="Node 22.5+ mit node:sqlite fehlt")
def test_dienst_lesezeichen():
    r = subprocess.run([_node_ok(), "--no-warnings", "--test", os.path.join(HIER, "dienst_lesezeichen.test.mjs")],
                       capture_output=True, text=True, cwd=os.path.dirname(HIER))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
