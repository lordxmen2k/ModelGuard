"""
Tests for the v0.2.0 Python library API.

These tests cover:
- aimodelguard.verify() returns a VerifyResult
- file_not_found, database_not_found, invalid_password
- happy path with approved model
- use case allowed/denied
- env-var password resolution
- VerifyResult.__bool__ for truthy checks
"""

import os
import sys
import tempfile
import gc
import time
from pathlib import Path
from contextlib import contextmanager

import pytest

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import aimodelguard
from aimodelguard.database import AIModelGuardDatabase


@contextmanager
def safe_tempdir():
    """Windows-safe temporary directory.

    tempfile.TemporaryDirectory() can fail on Windows because the OS holds
    SQLite file locks longer than the cleanup expects. This context manager
    uses mkdtemp() + manual cleanup with retry, so the same code works on
    Linux, macOS, and Windows.
    """
    tmpdir = tempfile.mkdtemp(prefix="aimodelguard-test-")
    try:
        yield Path(tmpdir)
    finally:
        gc.collect()
        time.sleep(0.05)
        try:
            for root, dirs, files in os.walk(tmpdir, topdown=False):
                for name in files:
                    for _ in range(3):
                        try:
                            os.unlink(os.path.join(root, name))
                            break
                        except (OSError, PermissionError):
                            time.sleep(0.1)
                    else:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except (OSError, PermissionError):
                        pass
            for _ in range(3):
                try:
                    os.rmdir(tmpdir)
                    break
                except (OSError, PermissionError):
                    time.sleep(0.1)
        except Exception:
            pass


def test_verify_returns_result_object():
    """verify() should return a VerifyResult instance, never raise on denial."""
    with safe_tempdir() as tmp:
        # No DB, no model — should return a result, not raise
        result = aimodelguard.verify(
            os.path.join(tmp, "nonexistent.gguf"),
            db_path=os.path.join(tmp, "no.db"),
        )
        assert isinstance(result, aimodelguard.VerifyResult)
        assert result.approved is False
        assert result.reason == "file_not_found"


def test_verify_file_not_found():
    """A non-existent model file returns file_not_found, not raise."""
    with safe_tempdir() as tmp:
        result = aimodelguard.verify(
            os.path.join(tmp, "missing.gguf"),
            db_path=os.path.join(tmp, "db.sqlite"),
            password="anything",
        )
        assert result.approved is False
        assert result.reason == "file_not_found"
        assert result.model_name == "missing.gguf"


def test_verify_database_not_found():
    """A non-existent DB returns database_not_found, not raise."""
    with safe_tempdir() as tmp:
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)
        result = aimodelguard.verify(
            str(model),
            db_path=os.path.join(tmp, "no-such-db.sqlite"),
            password="anything",
        )
        assert result.approved is False
        assert result.reason == "database_not_found"
        assert "db_path" in result.details


def test_verify_invalid_password():
    """Wrong password returns invalid_password, not raise."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        # Init with one password
        AIModelGuardDatabase(db_path, "correct_pw").close()

        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)

        result = aimodelguard.verify(str(model), db_path=db_path, password="wrong_pw")
        assert result.approved is False
        assert result.reason == "invalid_password"


def test_verify_happy_path():
    """An approved model returns approved=True with metadata."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)

        # Init + approve
        db = AIModelGuardDatabase(db_path, "pw")
        db.add_approved_model(
            model_path=str(model),
            sha256_hash=__import__("hashlib").sha256(model.read_bytes()).hexdigest(),
            approved_by="tester",
            publisher="Test Publisher",
            use_cases=["extraction", "chat"],
        )
        db.close()

        result = aimodelguard.verify(str(model), db_path=db_path, password="pw")
        assert result.approved is True
        assert result.reason == "approved"
        assert result.sha256_hash is not None
        assert result.publisher == "Test Publisher"
        assert result.use_cases == ["extraction", "chat"]


def test_verify_use_case_allowed():
    """When the use case is in the approved list, it's allowed."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)

        db = AIModelGuardDatabase(db_path, "pw")
        db.add_approved_model(
            model_path=str(model),
            sha256_hash=__import__("hashlib").sha256(model.read_bytes()).hexdigest(),
            approved_by="tester",
            use_cases=["extraction", "chat"],
        )
        db.close()

        result = aimodelguard.verify(str(model), use_case="extraction", db_path=db_path, password="pw")
        assert result.approved is True


def test_verify_use_case_denied():
    """When the use case is not in the approved list, it's denied."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)

        db = AIModelGuardDatabase(db_path, "pw")
        db.add_approved_model(
            model_path=str(model),
            sha256_hash=__import__("hashlib").sha256(model.read_bytes()).hexdigest(),
            approved_by="tester",
            use_cases=["extraction", "chat"],
        )
        db.close()

        result = aimodelguard.verify(str(model), use_case="code_generation", db_path=db_path, password="pw")
        assert result.approved is False
        assert result.reason == "use_case_not_allowed"


def test_verify_unapproved_model():
    """A model that's never been approved returns not_in_database."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        AIModelGuardDatabase(db_path, "pw").close()  # init only

        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)

        result = aimodelguard.verify(str(model), db_path=db_path, password="pw")
        assert result.approved is False
        assert result.reason == "not_in_database"


def test_verify_quarantined_model():
    """A quarantined model is denied even if it was previously approved."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)
        h = __import__("hashlib").sha256(model.read_bytes()).hexdigest()

        db = AIModelGuardDatabase(db_path, "pw", auto_backup=False)
        db.add_approved_model(
            model_path=str(model),
            sha256_hash=h,
            approved_by="tester",
        )
        db.quarantine_model(sha256_hash=h, reason="CVE-2026-TEST", quarantined_by="tester")
        db.close()

        result = aimodelguard.verify(str(model), db_path=db_path, password="pw")
        assert result.approved is False
        assert result.reason == "quarantined"


def test_verify_result_bool_is_approved():
    """`if aimodelguard.verify(path):` should be truthy iff approved."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)
        h = __import__("hashlib").sha256(model.read_bytes()).hexdigest()

        db = AIModelGuardDatabase(db_path, "pw")
        db.add_approved_model(model_path=str(model), sha256_hash=h, approved_by="t")
        db.close()

        r_approved = aimodelguard.verify(str(model), db_path=db_path, password="pw")
        r_denied = aimodelguard.verify(str(model), db_path=db_path, password="wrong")
        assert bool(r_approved) is True
        assert bool(r_denied) is False


def test_verify_env_var_password(monkeypatch):
    """If MODELGUARD_PASSWORD env var is set, the verify() call uses it."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)
        h = __import__("hashlib").sha256(model.read_bytes()).hexdigest()

        db = AIModelGuardDatabase(db_path, "secret")
        db.add_approved_model(model_path=str(model), sha256_hash=h, approved_by="t")
        db.close()

        monkeypatch.setenv("MODELGUARD_PASSWORD", "secret")
        # No password argument — should pick it up from env
        result = aimodelguard.verify(str(model), db_path=db_path)
        assert result.approved is True


def test_verify_password_arg_takes_precedence(monkeypatch):
    """If both env var and password arg are set, password arg wins."""
    with safe_tempdir() as tmp:
        db_path = os.path.join(tmp, "db.sqlite")
        model = Path(tmp) / "model.gguf"
        model.write_bytes(b"x" * 1024)
        h = __import__("hashlib").sha256(model.read_bytes()).hexdigest()

        db = AIModelGuardDatabase(db_path, "correct")
        db.add_approved_model(model_path=str(model), sha256_hash=h, approved_by="t")
        db.close()

        monkeypatch.setenv("MODELGUARD_PASSWORD", "WRONG")
        # password="correct" should win over the env var
        result = aimodelguard.verify(str(model), db_path=db_path, password="correct")
        assert result.approved is True


def test_version_string():
    """aimodelguard.__version__ should be a string starting with '0.'."""
    assert isinstance(aimodelguard.__version__, str)
    assert aimodelguard.__version__.startswith("0.")


def test_doi_constant():
    """aimodelguard.__doi__ should be the Zenodo DOI."""
    assert aimodelguard.__doi__ == "10.5281/zenodo.21578648"
    assert aimodelguard.__doi__.startswith("10.5281/zenodo.")
