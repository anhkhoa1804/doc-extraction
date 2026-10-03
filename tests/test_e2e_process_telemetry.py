from __future__ import annotations

import sys

import pytest

from benchmarks.scripts.e2e_process_telemetry import (
    MAX_SAMPLES,
    process_tree,
    sample_command,
)


def test_process_tree_includes_only_root_and_descendants():
    tree = process_tree(__import__("os").getpid())
    assert __import__("os").getpid() in tree
    assert all(pid > 0 and ticks >= 0 and rss >= 0 for pid, (ticks, rss) in tree.items())


def test_sample_command_is_bounded_and_does_not_record_arguments():
    result = sample_command(
        [sys.executable, "-c", "import time; time.sleep(.35)"],
        interval_seconds=0.25,
        max_wall_seconds=2,
    )
    assert result["return_code"] == 0
    assert result["wrapper_timeout"] is False
    assert result["sample_count"] <= MAX_SAMPLES
    assert result["executable"].startswith("python")
    assert "command" not in result
    assert "samples" in result
    assert all("gpu" in sample and "processes" in sample for sample in result["samples"])


def test_outer_timeout_cleans_only_owned_process_groups():
    result = sample_command(
        [
            sys.executable,
            "-c",
            "import subprocess,time; subprocess.Popen(['sleep','10'],start_new_session=True); time.sleep(10)",
        ],
        interval_seconds=0.25,
        max_wall_seconds=0.75,
    )
    assert result["wrapper_timeout"] is True
    assert result["wrapper_cleanup_verified"] is True


@pytest.mark.parametrize("interval", [0.01, 11])
def test_sample_interval_is_validated(interval):
    with pytest.raises(ValueError):
        sample_command([sys.executable, "-c", "pass"], interval_seconds=interval,
                       max_wall_seconds=2)
