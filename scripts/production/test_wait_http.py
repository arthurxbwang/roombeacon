"""A reload may return old-route 404 briefly; never declare a permanent failure healthy."""
import os
import subprocess
from pathlib import Path


def run_probe(tmp_path, success_after):
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    counter = tmp_path / 'count'
    counter.write_text('0')
    curl = bindir / 'curl'
    curl.write_text('''#!/usr/bin/env python3
import os, pathlib, sys
p=pathlib.Path(os.environ['PROBE_COUNTER'])
n=int(p.read_text())+1
p.write_text(str(n))
sys.exit(0 if n>=int(os.environ['PROBE_READY']) else 22)
''')
    curl.chmod(0o755)
    sleeper = bindir / 'sleep'
    sleeper.write_text('#!/bin/sh\nexit 0\n')
    sleeper.chmod(0o755)
    env = os.environ | {'PATH': str(bindir) + ':' + os.environ['PATH'], 'PROBE_COUNTER': str(counter),
                       'PROBE_READY': str(success_after)}
    result = subprocess.run(['bash', str(Path(__file__).with_name('wait-http.sh')), 'https://example.test/api'],
                            env=env, capture_output=True, text=True, timeout=10)
    return result.returncode, int(counter.read_text())


def test_transient_old_route_waits_until_new_workers_ready(tmp_path):
    assert run_probe(tmp_path, 3) == (0, 3)


def test_persistent_failure_is_not_healthy(tmp_path):
    assert run_probe(tmp_path, 100) == (1, 20)
