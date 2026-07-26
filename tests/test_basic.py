"""
Basic tests for ModelGuard.

Run with: python -m pytest tests/
Or: python tests/test_basic.py
"""

import os
import sys
import tempfile
import hashlib
import gc
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aimodelguard.database import AIModelGuardDatabase, compute_file_hash
from aimodelguard.backup import BackupManager


def test_compute_file_hash():
    """Test that file hashing works correctly."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"test content")
        temp_path = f.name

    try:
        hash1 = compute_file_hash(temp_path)
        hash2 = compute_file_hash(temp_path)

        # Same file should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 produces 64 hex characters

        # Verify against manual hash
        expected = hashlib.sha256(b"test content").hexdigest()
        assert hash1 == expected

        print("✓ test_compute_file_hash passed")
    finally:
        os.unlink(temp_path)


def test_database_init_and_approve():
    """Test database initialization and model approval."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        model_path = os.path.join(tmpdir, "test_model.gguf")

        # Create a fake model file
        with open(model_path, "wb") as f:
            f.write(b"fake model data" * 1000)

        # Initialize database
        db = AIModelGuardDatabase(db_path, "test_password_123")
        assert os.path.exists(db_path)

        # Approve a model
        model_hash = compute_file_hash(model_path)
        model_id = db.add_approved_model(
            model_path=model_path,
            sha256_hash=model_hash,
            approved_by="test_user",
            publisher="Test Publisher",
            use_cases=["testing"],
            expires_days=30
        )
        assert model_id > 0

        # Verify the model
        result = db.verify_model(model_path, use_case="testing")
        assert result["approved"] is True
        assert result["details"]["publisher"] == "Test Publisher"

        # Try to verify with wrong use case
        result = db.verify_model(model_path, use_case="production")
        assert result["approved"] is False
        assert result["reason"] == "use_case_not_allowed"

        # Try to verify a non-approved model
        other_path = os.path.join(tmpdir, "other_model.gguf")
        with open(other_path, "wb") as f:
            f.write(b"different model data")

        result = db.verify_model(other_path)
        assert result["approved"] is False
        assert result["reason"] == "not_in_database"

        db.close()
        print("✓ test_database_init_and_approve passed")


def test_backup_and_restore():
    """Test backup creation and restoration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        backup_dir = os.path.join(tmpdir, "backups")

        # Initialize database
        db = AIModelGuardDatabase(db_path, "test_password_123")

        # Add a model
        model_path = os.path.join(tmpdir, "test_model.gguf")
        with open(model_path, "wb") as f:
            f.write(b"test model data")

        model_hash = compute_file_hash(model_path)
        db.add_approved_model(
            model_path=model_path,
            sha256_hash=model_hash,
            approved_by="test_user"
        )

        # Create a backup
        backup_path = db.create_manual_backup(label="test")
        assert backup_path.exists()
        assert backup_path.suffix == ".gz"

        # Remove the model
        assert db.remove_approval(model_hash, "test_user") is True

        # Verify model is gone
        result = db.verify_model(model_path)
        assert result["approved"] is False

        # Restore from backup
        assert db.backup_manager.restore_backup(str(backup_path)) is True

        # Re-open database to verify
        db.close()
        db2 = AIModelGuardDatabase(db_path, "test_password_123", auto_backup=False)
        result = db2.verify_model(model_path)
        assert result["approved"] is True
        db2.close()

        print("✓ test_backup_and_restore passed")


def test_quarantine():
    """Test quarantine functionality."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        model_path = os.path.join(tmpdir, "test_model.gguf")

        with open(model_path, "wb") as f:
            f.write(b"test model data")

        db = AIModelGuardDatabase(db_path, "test_password_123")

        # Approve a model
        model_hash = compute_file_hash(model_path)
        db.add_approved_model(
            model_path=model_path,
            sha256_hash=model_hash,
            approved_by="test_user"
        )

        # Verify it's approved
        result = db.verify_model(model_path)
        assert result["approved"] is True

        # Quarantine it
        assert db.quarantine_model(model_hash, "CVE-2026-12345", "test_user") is True

        # Verify it's now blocked
        result = db.verify_model(model_path)
        assert result["approved"] is False
        assert result["reason"] == "quarantined"

        db.close()
        print("✓ test_quarantine passed")


def test_audit_log():
    """Test audit logging."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.sqlite")
        model_path = os.path.join(tmpdir, "test_model.gguf")

        with open(model_path, "wb") as f:
            f.write(b"test model data")

        db = AIModelGuardDatabase(db_path, "test_password_123")

        # Perform some operations
        model_hash = compute_file_hash(model_path)
        db.add_approved_model(
            model_path=model_path,
            sha256_hash=model_hash,
            approved_by="alice"
        )

        db.verify_model(model_path, user="bob", application="test_app")
        db.verify_model(model_path, user="bob", application="test_app")
        db.remove_approval(model_hash, "alice")

        # Check audit log
        entries = db.get_audit_log()
        assert len(entries) >= 4  # approve, verify, verify, remove

        # Check that events are logged
        event_types = [e["event_type"] for e in entries]
        assert "approve" in event_types
        assert "verify" in event_types
        assert "remove" in event_types

        db.close()
        print("✓ test_audit_log passed")


def test_password_verification():
    """Test that wrong password is rejected."""
    tmpdir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmpdir, "test.sqlite")

        # Initialize with one password
        db = AIModelGuardDatabase(db_path, "correct_password")
        db.close()

        # Try to open with wrong password
        try:
            db = AIModelGuardDatabase(db_path, "wrong_password")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Invalid master password" in str(e)

        # Should be able to open with correct password
        db = AIModelGuardDatabase(db_path, "correct_password", auto_backup=False)
        db.close()

        # Windows holds file locks briefly; give the OS time to release them
        # before we try to clean up. Also force garbage collection.
        gc.collect()
        time.sleep(0.1)

        print("✓ test_password_verification passed")
    finally:
        # Manual cleanup (avoids Windows file lock races with TemporaryDirectory).
        try:
            for root, dirs, files in os.walk(tmpdir, topdown=False):
                for name in files:
                    try:
                        os.unlink(os.path.join(root, name))
                    except (OSError, PermissionError):
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except (OSError, PermissionError):
                        pass
            try:
                os.rmdir(tmpdir)
            except (OSError, PermissionError):
                pass
        except Exception:
            pass


if __name__ == "__main__":
    test_compute_file_hash()
    test_database_init_and_approve()
    test_backup_and_restore()
    test_quarantine()
    test_audit_log()
    test_password_verification()
    print("\n✓ All tests passed!")
