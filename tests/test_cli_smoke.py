import subprocess
import sys
from pathlib import Path


def test_cli_help_runs():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "agentorchestrator.cli", "--help"],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"cli --help failed: {result.stderr}"
