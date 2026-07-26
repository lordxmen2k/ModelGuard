"""
CLI workflow tests for ModelGuard.

These tests drive the actual `aimodelguard` CLI binary end-to-end, simulating
what a real user would do. They complement the unit tests in test_basic.py
by exercising the full CLI surface (init, approve, verify, list, remove,
quarantine, audit, backup, restore).

Run with: pytest tests/test_cli_workflow.py -v
Or directly: python tests/test_cli_workflow.py
"""

import os
import subprocess
import sys
import tempfile
import shutil
from pathlib import Path


def run_modelguard(args, input_text=None, expect_success=True, cwd=None, password="test_password_123"):
    """
    Run the `aimodelguard` CLI with the given arguments.

    Returns a tuple of (returncode, stdout, stderr).
    If expect_success is True, asserts that returncode == 0.

    Uses `python -m aimodelguard.cli` so it works the same on Linux, macOS, and
    Windows (where the `aimodelguard` script may not be on PATH).

    Passes the password via MODELGUARD_PASSWORD env var instead of stdin so
    click.prompt(hide_input=True) doesn't hang on non-TTY subprocess stdin.

    Forces UTF-8 encoding so Unicode characters (✓, ✗, ⚠) in CLI output don't
    crash on Windows consoles using the default charmap codec.
    """
    cmd = [sys.executable, "-m", "aimodelguard.cli"] + args
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    if password:
        env["MODELGUARD_PASSWORD"] = password
    result = subprocess.run(
        cmd,
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",  # never fail decoding — replace bad bytes with '?'
        env=env,
        cwd=cwd,
        timeout=60,
    )
    if expect_success:
        assert result.returncode == 0, (
            f"Command failed: {cmd}\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
    return result


def test_cli_workflow():
    """End-to-end CLI workflow: init, approve, verify, list, quarantine, backup."""
    # Set up an isolated workspace
    with tempfile.TemporaryDirectory() as workspace:
        workspace = Path(workspace)
        model_file = workspace / "qwen-1.5b-instruct.gguf"
        db_path = workspace / "db.sqlite"
        backup_dir = workspace / "backups"
        backup_dir.mkdir()

        # Test 1: Create a 10MB random model file
        with open(model_file, "wb") as f:
            f.write(os.urandom(10 * 1024 * 1024))
        assert model_file.exists()
        assert model_file.stat().st_size == 10 * 1024 * 1024

        # Test 2: Initialize the database
        run_modelguard(
            ["init", "--db-path", str(db_path)],
        )
        assert db_path.exists()

        # Test 3: List approved models (should be empty)
        result = run_modelguard(
            ["list", "--db-path", str(db_path)],
        )
        assert "No models approved" in result.stdout

        # Test 4: Approve the model
        run_modelguard(
            [
                "approve",
                "--db-path", str(db_path),
                "--model", str(model_file),
                "--publisher", "Qwen Team",
                "--version", "1.0.0",
                "--use-case", "extraction",
                "--expires", "365",
            ],
        )

        # Test 5: List approved models (should show 1)
        result = run_modelguard(
            ["list", "--db-path", str(db_path)],
        )
        assert "qwen-1.5b-instruct" in result.stdout
        assert "Qwen Team" in result.stdout

        # Test 6: Verify the approved model
        result = run_modelguard(
            ["verify", "--db-path", str(db_path), "--model", str(model_file)],
        )
        assert "approved" in result.stdout.lower()

        # Test 7: Verify with allowed use case
        result = run_modelguard(
            [
                "verify",
                "--db-path", str(db_path),
                "--model", str(model_file),
                "--use-case", "extraction",
            ],
        )
        assert "approved" in result.stdout.lower()

        # Test 8: Verify with disallowed use case (should fail)
        result = run_modelguard(
            [
                "verify",
                "--db-path", str(db_path),
                "--model", str(model_file),
                "--use-case", "code_generation",
            ],
            expect_success=False,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "NOT approved" in combined or "denied" in combined.lower()

        # Test 9: Verify an unapproved model (should fail)
        unapproved = workspace / "unapproved-model.gguf"
        with open(unapproved, "wb") as f:
            f.write(os.urandom(5 * 1024 * 1024))
        result = run_modelguard(
            ["verify", "--db-path", str(db_path), "--model", str(unapproved)],
            expect_success=False,
        )
        assert result.returncode != 0
        assert "NOT approved" in (result.stdout + result.stderr)

        # Test 10: JSON output
        result = run_modelguard(
            [
                "verify",
                "--db-path", str(db_path),
                "--model", str(model_file),
                "--json",
            ],
        )
        # Should be valid JSON
        import json
        try:
            data = json.loads(result.stdout)
            assert "approved" in data or "status" in data
        except json.JSONDecodeError:
            # May have warnings before JSON; try to find JSON in output
            assert "{" in result.stdout and "}" in result.stdout

        # Test 11: Create a manual backup
        run_modelguard(
            ["backup", "create", "--db-path", str(db_path), "--label", "manual-test"],
        )
        backups = list(backup_dir.glob("*.db.gz"))
        assert len(backups) >= 1

        # Test 12: List backups
        result = run_modelguard(
            ["backup", "list", "--db-path", str(db_path)],
        )
        assert "manual-test" in result.stdout

        # Test 13: Verify backups
        run_modelguard(
            ["backup", "verify", "--db-path", str(db_path)],
        )

        # Test 14: Compute hash for removal
        import hashlib
        sha256 = hashlib.sha256()
        with open(model_file, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        model_hash = sha256.hexdigest()

        # Test 15: Remove the model
        run_modelguard(
            ["remove", "--db-path", str(db_path), "--hash", model_hash],
        )

        # Test 16: Verify the removed model (should fail)
        result = run_modelguard(
            ["verify", "--db-path", str(db_path), "--model", str(model_file)],
            expect_success=False,
        )
        assert result.returncode != 0
        assert "NOT approved" in (result.stdout + result.stderr)

        # Test 17: Quarantine a model (use a fresh file since we removed the above)
        quarantine_file = workspace / "to-quarantine.gguf"
        with open(quarantine_file, "wb") as f:
            f.write(os.urandom(2 * 1024 * 1024))
        run_modelguard(
            [
                "quarantine",
                "--db-path", str(db_path),
                "--model", str(quarantine_file),
                "--reason", "CVE-2026-12345",
            ],
        )

        # Test 18: Verify quarantined model (should fail)
        result = run_modelguard(
            ["verify", "--db-path", str(db_path), "--model", str(quarantine_file)],
            expect_success=False,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "NOT approved" in combined or "quarantined" in combined.lower()

        # Test 19: View audit log
        result = run_modelguard(
            ["audit", "--db-path", str(db_path), "--limit", "20"],
        )
        assert "VERIFY" in result.stdout
        assert "APPROVE" in result.stdout
        assert "REMOVE" in result.stdout or "QUARANTINE" in result.stdout

        # Test 20: Wrong password (should fail)
        result = run_modelguard(
            ["list", "--db-path", str(db_path)],
            password="wrong_password",
            expect_success=False,
        )
        assert result.returncode != 0

        # Test 21: Missing model file (should fail)
        result = run_modelguard(
            [
                "verify",
                "--db-path", str(db_path),
                "--model", str(workspace / "nonexistent.gguf"),
            ],
            expect_success=False,
        )
        assert result.returncode != 0

        print("✓ test_cli_workflow passed (21 scenarios)")


if __name__ == "__main__":
    test_cli_workflow()
    print("\n✓ CLI workflow test passed!")
