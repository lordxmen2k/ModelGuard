"""
AI Model Guard backup system — Automatic backups to protect against database corruption.

The backup system ensures that if the main database is corrupted, the user can
restore from a recent backup without losing their approved model list.
"""

import shutil
import gzip
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
import hashlib


class BackupManager:
    """Manages automatic and manual backups of the ModelGuard database."""

    def __init__(self, db_path: str, backup_dir: Optional[str] = None, max_backups: int = 10):
        """
        Initialize the backup manager.

        Args:
            db_path: Path to the main database file
            backup_dir: Directory to store backups (defaults to db_path/backups/)
            max_backups: Maximum number of backups to keep (oldest are deleted)
        """
        self.db_path = Path(db_path)
        self.backup_dir = Path(backup_dir) if backup_dir else self.db_path.parent / "backups"
        self.max_backups = max_backups
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: Optional[str] = None) -> Path:
        """
        Create a backup of the database.

        Args:
            label: Optional label for the backup (e.g., "before-upgrade")

        Returns:
            Path to the backup file
        """
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        # Generate backup filename
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        if label:
            label_clean = "".join(c if c.isalnum() or c in "-_" else "-" for c in label)
            backup_name = f"aimodelguard-backup-{timestamp}-{label_clean}.db.gz"
        else:
            backup_name = f"aimodelguard-backup-{timestamp}.db.gz"

        backup_path = self.backup_dir / backup_name

        # Create compressed backup
        with open(self.db_path, "rb") as f_in:
            with gzip.open(backup_path, "wb", compresslevel=9) as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Set restrictive permissions
        os.chmod(backup_path, 0o600)

        # Clean up old backups
        self._cleanup_old_backups()

        return backup_path

    def list_backups(self) -> List[dict]:
        """
        List all available backups.

        Returns:
            List of backup info dictionaries, sorted by timestamp (newest first)
        """
        backups = []

        for backup_file in self.backup_dir.glob("aimodelguard-backup-*.db.gz"):
            stat = backup_file.stat()
            backups.append({
                "path": str(backup_file),
                "name": backup_file.name,
                "size_bytes": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "compressed": True
            })

        # Sort by creation time (newest first)
        backups.sort(key=lambda x: x["created"], reverse=True)
        return backups

    def restore_backup(self, backup_path: str, verify: bool = True) -> bool:
        """
        Restore the database from a backup.

        Args:
            backup_path: Path to the backup file
            verify: If True, verify the backup before restoring

        Returns:
            True if restore was successful

        WARNING: This overwrites the current database!
        """
        backup_path = Path(backup_path)

        if not backup_path.exists():
            raise FileNotFoundError(f"Backup not found: {backup_path}")

        # Verify backup integrity
        if verify:
            if not self._verify_backup(backup_path):
                raise ValueError(f"Backup verification failed: {backup_path}")

        # Create a safety backup of the current database before restoring
        if self.db_path.exists():
            safety_backup = self.create_backup(label="before-restore")
            print(f"Created safety backup: {safety_backup}")

        # Restore from backup
        with gzip.open(backup_path, "rb") as f_in:
            with open(self.db_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

        # Set restrictive permissions
        os.chmod(self.db_path, 0o600)

        return True

    def _verify_backup(self, backup_path: Path) -> bool:
        """Verify a backup file is not corrupted."""
        try:
            # Try to decompress and read
            with gzip.open(backup_path, "rb") as f:
                # Read a small chunk to verify it's a valid SQLite database
                header = f.read(16)
                # SQLite databases start with "SQLite format 3\000"
                if not header.startswith(b"SQLite format 3"):
                    return False
            return True
        except Exception:
            return False

    def _cleanup_old_backups(self):
        """Remove old backups beyond the retention limit."""
        backups = self.list_backups()

        if len(backups) > self.max_backups:
            # Delete oldest backups
            for backup in backups[self.max_backups:]:
                try:
                    Path(backup["path"]).unlink()
                except Exception as e:
                    print(f"Warning: Could not delete old backup {backup['path']}: {e}")

    def verify_all_backups(self) -> dict:
        """
        Verify all backups and return a report.

        Returns:
            Dictionary with verification results
        """
        backups = self.list_backups()
        results = {
            "total": len(backups),
            "valid": 0,
            "invalid": 0,
            "details": []
        }

        for backup in backups:
            backup_path = Path(backup["path"])
            is_valid = self._verify_backup(backup_path)

            if is_valid:
                results["valid"] += 1
            else:
                results["invalid"] += 1

            results["details"].append({
                "name": backup["name"],
                "valid": is_valid,
                "size_bytes": backup["size_bytes"]
            })

        return results
