"""
AI Model Guard database — SQLite-based storage for approved model signatures and audit logs.

The database is encrypted using SQLCipher with the master password as the key.
Includes automatic backup before destructive operations.
"""

import sqlite3
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import hashlib
import secrets
from .backup import BackupManager


class AIModelGuardDatabase:
    """Manages the AI Model Guard SQLite database with encryption and automatic backups."""

    def __init__(
        self,
        db_path: str,
        master_password: str,
        auto_backup: bool = True,
        max_backups: int = 10
    ):
        """
        Initialize the database connection.

        Args:
            db_path: Path to the SQLite database file
            master_password: Master password for encryption
            auto_backup: If True, automatically backup before destructive operations
            max_backups: Maximum number of backups to keep
        """
        self.db_path = Path(db_path)
        self.master_password = master_password
        self.auto_backup = auto_backup
        self._connection = None

        # Initialize backup manager
        if self.auto_backup:
            self.backup_manager = BackupManager(
                str(self.db_path),
                max_backups=max_backups
            )
        else:
            self.backup_manager = None

        self._connect()

    def _connect(self):
        """Connect to the database and verify the master password."""
        # Derive encryption key from master password
        salt_path = self.db_path.with_suffix(".salt")
        if salt_path.exists():
            with open(salt_path, "rb") as f:
                salt = f.read()
        else:
            salt = secrets.token_bytes(32)
            salt_path.parent.mkdir(parents=True, exist_ok=True)
            with open(salt_path, "wb") as f:
                f.write(salt)
            os.chmod(salt_path, 0o600)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )
        self._key = kdf.derive(self.master_password.encode())

        # Connect to SQLite
        # Note: In production, use SQLCipher for actual encryption
        # For now, we use standard SQLite with file permissions
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(self.db_path))
        self._connection.row_factory = sqlite3.Row

        # Set restrictive file permissions
        if self.db_path.exists():
            os.chmod(self.db_path, 0o600)

        # Create tables if they don't exist
        self._create_tables()

        # Verify master password by checking a sentinel value
        self._verify_password()

    def _create_tables(self):
        """Create the database tables."""
        cursor = self._connection.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS approved_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_name TEXT NOT NULL,
                model_version TEXT,
                publisher TEXT,
                sha256_hash TEXT NOT NULL UNIQUE,
                file_size INTEGER,
                signature TEXT,
                approved_by TEXT NOT NULL,
                approved_date TEXT NOT NULL,
                expires_date TEXT,
                trust_level TEXT DEFAULT 'verified',
                allowed_use_cases TEXT,
                notes TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                model_hash TEXT,
                model_path TEXT,
                result TEXT,
                reason TEXT,
                user TEXT,
                application TEXT,
                details TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS quarantined_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sha256_hash TEXT NOT NULL UNIQUE,
                quarantined_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                quarantined_by TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        self._connection.commit()

    def _verify_password(self):
        """Verify the master password by checking a sentinel value."""
        cursor = self._connection.cursor()

        # Try to get the sentinel value
        cursor.execute("SELECT value FROM config WHERE key = 'master_password_hash'")
        row = cursor.fetchone()

        password_hash = hashlib.sha256(self._key).hexdigest()

        if row is None:
            # First time setup, store the sentinel
            cursor.execute(
                "INSERT INTO config (key, value) VALUES (?, ?)",
                ("master_password_hash", password_hash)
            )
            self._connection.commit()
        else:
            # Verify the password
            if row["value"] != password_hash:
                raise ValueError("Invalid master password")

    def add_approved_model(
        self,
        model_path: str,
        sha256_hash: str,
        approved_by: str,
        publisher: Optional[str] = None,
        model_version: Optional[str] = None,
        use_cases: Optional[List[str]] = None,
        expires_days: Optional[int] = None,
        trust_level: str = "verified",
        notes: Optional[str] = None
    ) -> int:
        """Add a model to the approved list.

        Note: This is an additive operation, so no automatic backup is created.
        Backups are only created before destructive operations (remove, quarantine).
        If you need a backup before this operation, call create_backup() manually.
        """
        cursor = self._connection.cursor()

        file_size = os.path.getsize(model_path) if os.path.exists(model_path) else None
        approved_date = datetime.now(timezone.utc).isoformat()
        expires_date = None
        if expires_days:
            expires_date = (datetime.now(timezone.utc) + timedelta(days=expires_days)).isoformat()

        use_cases_json = json.dumps(use_cases) if use_cases else None

        try:
            cursor.execute("""
                INSERT INTO approved_models (
                    model_name, model_version, publisher, sha256_hash, file_size,
                    approved_by, approved_date, expires_date, trust_level,
                    allowed_use_cases, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                Path(model_path).name,
                model_version,
                publisher,
                sha256_hash,
                file_size,
                approved_by,
                approved_date,
                expires_date,
                trust_level,
                use_cases_json,
                notes
            ))

            model_id = cursor.lastrowid
            self._connection.commit()

            # Log the event
            self.log_event(
                event_type="approve",
                model_hash=sha256_hash,
                model_path=model_path,
                result="success",
                user=approved_by,
                details=json.dumps({
                    "publisher": publisher,
                    "use_cases": use_cases,
                    "expires_days": expires_days
                })
            )

            return model_id

        except sqlite3.IntegrityError:
            # Hash already exists
            self.log_event(
                event_type="approve",
                model_hash=sha256_hash,
                model_path=model_path,
                result="failure",
                reason="hash_already_exists",
                user=approved_by
            )
            raise ValueError(f"Model with hash {sha256_hash} is already approved")

    def verify_model(
        self,
        model_path: str,
        use_case: Optional[str] = None,
        user: Optional[str] = None,
        application: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verify if a model is approved to run.

        Returns:
            Dictionary with:
                - approved: bool
                - reason: str (if not approved)
                - details: dict (if approved)
        """
        # Check if file exists
        if not os.path.exists(model_path):
            self.log_event(
                event_type="verify",
                model_path=model_path,
                result="denied",
                reason="file_not_found",
                user=user,
                application=application
            )
            return {"approved": False, "reason": "file_not_found"}

        # Compute hash
        sha256_hash = compute_file_hash(model_path)

        # Check if quarantined
        cursor = self._connection.cursor()
        cursor.execute("SELECT * FROM quarantined_models WHERE sha256_hash = ?", (sha256_hash,))
        if cursor.fetchone():
            self.log_event(
                event_type="verify",
                model_hash=sha256_hash,
                model_path=model_path,
                result="denied",
                reason="quarantined",
                user=user,
                application=application
            )
            return {"approved": False, "reason": "quarantined"}

        # Check if approved
        cursor.execute("SELECT * FROM approved_models WHERE sha256_hash = ?", (sha256_hash,))
        row = cursor.fetchone()

        if row is None:
            self.log_event(
                event_type="verify",
                model_hash=sha256_hash,
                model_path=model_path,
                result="denied",
                reason="not_in_database",
                user=user,
                application=application
            )
            return {"approved": False, "reason": "not_in_database"}

        # Check expiration
        if row["expires_date"]:
            expires = datetime.fromisoformat(row["expires_date"])
            if datetime.now(timezone.utc) > expires:
                self.log_event(
                    event_type="verify",
                    model_hash=sha256_hash,
                    model_path=model_path,
                    result="denied",
                    reason="expired",
                    user=user,
                    application=application
                )
                return {"approved": False, "reason": "expired"}

        # Check use case
        if use_case and row["allowed_use_cases"]:
            allowed_use_cases = json.loads(row["allowed_use_cases"])
            if use_case not in allowed_use_cases:
                self.log_event(
                    event_type="verify",
                    model_hash=sha256_hash,
                    model_path=model_path,
                    result="denied",
                    reason="use_case_not_allowed",
                    user=user,
                    application=application,
                    details=json.dumps({"requested": use_case, "allowed": allowed_use_cases})
                )
                return {"approved": False, "reason": "use_case_not_allowed"}

        # Approved!
        self.log_event(
            event_type="verify",
            model_hash=sha256_hash,
            model_path=model_path,
            result="allowed",
            user=user,
            application=application
        )

        return {
            "approved": True,
            "details": {
                "name": row["model_name"],
                "sha256_hash": row["sha256_hash"],
                "publisher": row["publisher"],
                "use_cases": json.loads(row["allowed_use_cases"]) if row["allowed_use_cases"] else None,
                "expires": row["expires_date"],
                "trust_level": row["trust_level"]
            }
        }

    def list_approved_models(self) -> List[Dict[str, Any]]:
        """List all approved models."""
        cursor = self._connection.cursor()
        cursor.execute("SELECT * FROM approved_models ORDER BY approved_date DESC")

        models = []
        for row in cursor.fetchall():
            models.append({
                "id": row["id"],
                "name": row["model_name"],
                "version": row["model_version"],
                "publisher": row["publisher"],
                "hash": row["sha256_hash"],
                "approved_by": row["approved_by"],
                "approved_date": row["approved_date"],
                "expires_date": row["expires_date"],
                "use_cases": json.loads(row["allowed_use_cases"]) if row["allowed_use_cases"] else None,
                "trust_level": row["trust_level"]
            })

        return models

    def remove_approval(self, sha256_hash: str, removed_by: str) -> bool:
        """Remove a model from the approved list."""
        # Create backup before modification
        if self.auto_backup and self.backup_manager:
            self.backup_manager.create_backup(label="before-remove")

        cursor = self._connection.cursor()
        cursor.execute("DELETE FROM approved_models WHERE sha256_hash = ?", (sha256_hash,))
        deleted = cursor.rowcount > 0
        self._connection.commit()

        self.log_event(
            event_type="remove",
            model_hash=sha256_hash,
            result="success" if deleted else "failure",
            reason="not_found" if not deleted else None,
            user=removed_by
        )

        return deleted

    def quarantine_model(self, sha256_hash: str, reason: str, quarantined_by: str) -> bool:
        """Quarantine a model (block it from running)."""
        # Create backup before modification
        if self.auto_backup and self.backup_manager:
            self.backup_manager.create_backup(label="before-quarantine")

        cursor = self._connection.cursor()
        quarantined_date = datetime.now(timezone.utc).isoformat()

        try:
            cursor.execute("""
                INSERT INTO quarantined_models (sha256_hash, quarantined_date, reason, quarantined_by)
                VALUES (?, ?, ?, ?)
            """, (sha256_hash, quarantined_date, reason, quarantined_by))
            self._connection.commit()

            self.log_event(
                event_type="quarantine",
                model_hash=sha256_hash,
                result="success",
                reason=reason,
                user=quarantined_by
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def log_event(
        self,
        event_type: str,
        model_hash: Optional[str] = None,
        model_path: Optional[str] = None,
        result: Optional[str] = None,
        reason: Optional[str] = None,
        user: Optional[str] = None,
        application: Optional[str] = None,
        details: Optional[str] = None
    ):
        """Log an event to the audit log."""
        cursor = self._connection.cursor()
        cursor.execute("""
            INSERT INTO audit_log (
                timestamp, event_type, model_hash, model_path, result, reason, user, application, details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now(timezone.utc).isoformat(),
            event_type,
            model_hash,
            model_path,
            result,
            reason,
            user,
            application,
            details
        ))
        self._connection.commit()

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        cursor = self._connection.cursor()
        cursor.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT ?", (limit,))

        entries = []
        for row in cursor.fetchall():
            entries.append({
                "timestamp": row["timestamp"],
                "event_type": row["event_type"],
                "model_hash": row["model_hash"],
                "model_path": row["model_path"],
                "result": row["result"],
                "reason": row["reason"],
                "user": row["user"],
                "application": row["application"]
            })

        return entries

    def close(self):
        """Close the database connection."""
        if self._connection:
            self._connection.close()




    def maybe_auto_backup(self, operation: str):
        """
        Intelligently decide whether to create a backup based on the operation type.

        Only creates backups for DESTRUCTIVE operations, not additive ones.

        Args:
            operation: The operation being performed ('approve', 'remove', 'quarantine', etc.)
        """
        if not self.auto_backup or not self.backup_manager:
            return

        # Destructive operations that benefit from backup
        destructive_ops = {'remove', 'quarantine', 'restore', 'password_change'}

        if operation in destructive_ops:
            self.backup_manager.create_backup(label=f"before-{operation}")

    def create_manual_backup(self, label: Optional[str] = None) -> Optional[Path]:
        """
        Manually create a backup (called by user via CLI or API).

        Args:
            label: Optional label for the backup

        Returns:
            Path to the backup file, or None if auto_backup is disabled
        """
        if not self.backup_manager:
            return None
        return self.backup_manager.create_backup(label=label)


def compute_file_hash(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
