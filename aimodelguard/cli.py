"""
AI Model Guard CLI — Command-line interface for managing approved AI model signatures.
"""

import click
import getpass
import json
import os
import sys
from pathlib import Path
from .database import AIModelGuardDatabase, compute_file_hash
from .backup import BackupManager

# Reconfigure stdout/stderr to UTF-8 so Unicode glyphs (✓, ✗, ⚠) work on
# Windows consoles that default to charmap encoding. Safe no-op on POSIX.
# Done at import time so it takes effect before any subcommand runs.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except (AttributeError, OSError):
    pass


def get_master_password(confirm: bool = False) -> str:
    """Prompt for the master password.

    Uses click.prompt(hide_input=True) instead of getpass because the latter
    has known issues on Windows when stdin is not a real TTY (e.g., piped
    input, subprocess, IDE consoles). click.prompt handles all of these cases
    correctly across platforms.

    Priority for password source:
      1. MODELGUARD_PASSWORD environment variable (for CI/automation)
      2. Interactive prompt (hidden input)
    """
    # Allow non-interactive use via environment variable
    env_pw = os.environ.get("MODELGUARD_PASSWORD")
    if env_pw:
        return env_pw

    if confirm:
        password = click.prompt("Enter master password", hide_input=True, confirmation_prompt=True)
        return password
    return click.prompt("Enter master password", hide_input=True)


@click.group()
@click.version_option()
def cli():
    """AI Model Guard — Manage an allowlist of approved AI model signatures."""
    # Reconfigure stdout/stderr to UTF-8 so Unicode glyphs (✓, ✗, ⚠) work on
    # Windows consoles that default to charmap encoding. Safe no-op on POSIX.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


@cli.command()
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def init(db_path):
    """Initialize the AI Model Guard database (one-time setup)."""
    db_path = Path(db_path).expanduser()

    if db_path.exists():
        click.echo(f"✗ Database already exists at {db_path}", err=True)
        click.echo("Use 'aimodelguard list' to see approved models.", err=True)
        sys.exit(1)

    click.echo("Initializing AI Model Guard database...")
    click.echo("You'll be asked to set a master password.")
    click.echo("This password will be required for all operations.")
    click.echo("")

    password = get_master_password(confirm=True)

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        db.log_event(event_type="init", user="system")
        db.close()

        click.echo("")
        click.echo(f"✓ Database initialized at {db_path}")
        click.echo("✓ Master password set")
        click.echo("")
        click.echo("Next steps:")
        click.echo("  1. Approve a model: aimodelguard approve --model <path>")
        click.echo("  2. List approved models: aimodelguard list")
        click.echo("  3. Verify a model: aimodelguard verify --model <path>")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", required=True, help="Path to the model file")
@click.option("--publisher", "-p", help="Model publisher (e.g., 'Qwen Team')")
@click.option("--version", "-v", "model_version", help="Model version")
@click.option(
    "--use-case",
    "-u",
    multiple=True,
    help="Allowed use cases (can be specified multiple times)"
)
@click.option(
    "--expires",
    "-e",
    type=int,
    help="Days until expiration (e.g., 365 for 1 year)"
)
@click.option(
    "--trust-level",
    default="verified",
    type=click.Choice(["verified", "community", "experimental"]),
    help="Trust level"
)
@click.option("--notes", "-n", help="Additional notes")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def approve(model, publisher, model_version, use_case, expires, trust_level, notes, db_path):
    """Approve a model to run on this system."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        click.echo("Run 'aimodelguard init' first.", err=True)
        sys.exit(1)

    if not Path(model).exists():
        click.echo(f"✗ Model file not found: {model}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)

        # Compute hash
        click.echo(f"Computing hash of {model}...")
        sha256_hash = compute_file_hash(model)

        # Get username (from environment or prompt)
        import os
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

        # Add to database
        model_id = db.add_approved_model(
            model_path=model,
            sha256_hash=sha256_hash,
            approved_by=user,
            publisher=publisher,
            model_version=model_version,
            use_cases=list(use_case) if use_case else None,
            expires_days=expires,
            trust_level=trust_level,
            notes=notes
        )

        click.echo("")
        click.echo("✓ Model approved")
        click.echo(f"  Name: {Path(model).name}")
        click.echo(f"  Hash: {sha256_hash}")
        if publisher:
            click.echo(f"  Publisher: {publisher}")
        if model_version:
            click.echo(f"  Version: {model_version}")
        if use_case:
            click.echo(f"  Use cases: {', '.join(use_case)}")
        if expires:
            from datetime import datetime, timezone, timedelta
            expires_date = (datetime.now(timezone.utc) + timedelta(days=expires)).isoformat()
            click.echo(f"  Expires: {expires_date}")
        click.echo(f"  Approved by: {user}")

        db.close()

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", required=True, help="Path to the model file")
@click.option("--use-case", "-u", help="Intended use case")
@click.option("--user", help="User requesting verification")
@click.option("--application", help="Application requesting verification")
@click.option("--json", "output_json", is_flag=True, help="Output as JSON")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def verify(model, use_case, user, application, output_json, db_path):
    """Verify if a model is approved to run."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        if not output_json:
            click.echo(f"✗ Database not found at {db_path}", err=True)
        else:
            print(json.dumps({"approved": False, "reason": "database_not_found"}))
        sys.exit(1)

    if not Path(model).exists():
        if not output_json:
            click.echo(f"✗ Model file not found: {model}", err=True)
        else:
            print(json.dumps({"approved": False, "reason": "file_not_found"}))
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        result = db.verify_model(
            model_path=model,
            use_case=use_case,
            user=user,
            application=application
        )
        db.close()

        if output_json:
            print(json.dumps(result, indent=2))
        else:
            if result["approved"]:
                click.echo("✓ Model is approved")
                details = result.get("details", {})
                if details.get("publisher"):
                    click.echo(f"  Publisher: {details['publisher']}")
                if details.get("use_cases"):
                    click.echo(f"  Use cases: {', '.join(details['use_cases'])}")
                if details.get("expires"):
                    click.echo(f"  Expires: {details['expires']}")
            else:
                click.echo(f"✗ Model is NOT approved: {result['reason']}", err=True)
                click.echo(f"  File: {model}", err=True)
                click.echo("", err=True)
                click.echo("To approve this model, run:", err=True)
                click.echo(f"  aimodelguard approve --model {model}", err=True)
                sys.exit(1)

    except Exception as e:
        if output_json:
            print(json.dumps({"approved": False, "reason": "error", "error": str(e)}))
        else:
            click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command(name="list")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def list_models(db_path):
    """List all approved models."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        models = db.list_approved_models()
        db.close()

        if not models:
            click.echo("No models approved yet.")
            click.echo("Approve a model with: aimodelguard approve --model <path>")
            return

        click.echo(f"Approved Models ({len(models)}):")
        click.echo("")

        for i, model in enumerate(models, 1):
            click.echo(f"{i}. {model['name']}")
            if model['version']:
                click.echo(f"   Version: {model['version']}")
            if model['publisher']:
                click.echo(f"   Publisher: {model['publisher']}")
            click.echo(f"   Hash: {model['hash'][:16]}...")
            if model['use_cases']:
                click.echo(f"   Use cases: {', '.join(model['use_cases'])}")
            click.echo(f"   Approved: {model['approved_date']}")
            if model['expires_date']:
                click.echo(f"   Expires: {model['expires_date']}")
            click.echo(f"   Approved by: {model['approved_by']}")
            click.echo("")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--hash", "sha256_hash", required=True, help="SHA-256 hash of the model to remove")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def remove(sha256_hash, db_path):
    """Remove a model from the approved list."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        import os
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        success = db.remove_approval(sha256_hash, user)
        db.close()

        if success:
            click.echo("✓ Model removed from approved list")
        else:
            click.echo(f"✗ Model with hash {sha256_hash} not found", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--model", "-m", help="Path to the model file")
@click.option("--hash", "sha256_hash", help="SHA-256 hash of the model")
@click.option("--reason", "-r", required=True, help="Reason for quarantine")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def quarantine(model, sha256_hash, reason, db_path):
    """Quarantine a model (block it from running)."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    if not model and not sha256_hash:
        click.echo("✗ Must provide either --model or --hash", err=True)
        sys.exit(1)

    if model:
        if not Path(model).exists():
            click.echo(f"✗ Model file not found: {model}", err=True)
            sys.exit(1)
        click.echo(f"Computing hash of {model}...")
        sha256_hash = compute_file_hash(model)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        import os
        user = os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"
        success = db.quarantine_model(sha256_hash, reason, user)
        db.close()

        if success:
            click.echo("")
            click.echo("⚠ Model quarantined")
            click.echo(f"  Hash: {sha256_hash}")
            click.echo(f"  Reason: {reason}")
            click.echo(f"  Quarantined by: {user}")
            click.echo("")
            click.echo("This model is now blocked from running.")
        else:
            click.echo(f"✗ Model with hash {sha256_hash} is already quarantined", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--limit", "-n", default=50, help="Number of entries to show")
@click.option("--event-type", help="Filter by event type (approve, verify, remove, quarantine)")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def audit(limit, event_type, db_path):
    """Show the audit log."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password)
        entries = db.get_audit_log(limit=limit)
        db.close()

        if event_type:
            entries = [e for e in entries if e['event_type'] == event_type]

        if not entries:
            click.echo("No audit log entries found.")
            return

        click.echo(f"Audit Log (Last {len(entries)} entries):")
        click.echo("")

        for entry in entries:
            timestamp = entry['timestamp'][:19]  # Trim microseconds
            event = entry['event_type'].upper().ljust(12)
            result = entry.get('result', '').upper() if entry.get('result') else ''
            user = entry.get('user', '')
            model_path = entry.get('model_path', '')
            reason = entry.get('reason', '')

            line = f"{timestamp} | {event} | {result}"
            if model_path:
                line += f" | {Path(model_path).name}"
            if user:
                line += f" | {user}"
            if reason:
                line += f" | {reason}"

            click.echo(line)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)




@cli.group()
def backup():
    """Manage database backups."""
    pass


@backup.command(name="create")
@click.option("--label", "-l", help="Optional label for the backup")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def backup_create(label, db_path):
    """Create a manual backup of the database."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        # auto_backup=True so we have a backup_manager for manual backup creation
        db = AIModelGuardDatabase(str(db_path), password, auto_backup=True)
        backup_path = db.backup_manager.create_backup(label=label)
        db.close()

        click.echo("")
        click.echo("✓ Backup created")
        click.echo(f"  Path: {backup_path}")
        click.echo(f"  Size: {backup_path.stat().st_size:,} bytes")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@backup.command(name="list")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def backup_list(db_path):
    """List all available backups."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password, auto_backup=True)
        backups = db.backup_manager.list_backups()
        db.close()

        if not backups:
            click.echo("No backups found.")
            return

        click.echo(f"Available Backups ({len(backups)}):")
        click.echo("")

        for i, backup in enumerate(backups, 1):
            click.echo(f"{i}. {backup['name']}")
            click.echo(f"   Created: {backup['created']}")
            click.echo(f"   Size: {backup['size_bytes']:,} bytes")
            click.echo(f"   Path: {backup['path']}")
            click.echo("")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@backup.command(name="restore")
@click.argument("backup_path")
@click.option("--no-verify", is_flag=True, help="Skip backup verification")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def backup_restore(backup_path, no_verify, db_path):
    """Restore the database from a backup."""
    db_path = Path(db_path).expanduser()

    click.echo("⚠ WARNING: This will overwrite the current database!")
    click.echo("")

    if not click.confirm("Are you sure you want to continue?"):
        click.echo("Restore cancelled.")
        return

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password, auto_backup=True)
        success = db.backup_manager.restore_backup(
            backup_path,
            verify=not no_verify
        )
        db.close()

        if success:
            click.echo("")
            click.echo("✓ Database restored successfully")
            click.echo(f"  From: {backup_path}")
            click.echo(f"  To: {db_path}")
            click.echo("")
            click.echo("Please restart any applications using ModelGuard.")
        else:
            click.echo("✗ Restore failed", err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@backup.command(name="verify")
@click.option(
    "--db-path",
    default="~/.aimodelguard/db.sqlite",
    help="Path to the database file"
)
def backup_verify(db_path):
    """Verify all backups are not corrupted."""
    db_path = Path(db_path).expanduser()

    if not db_path.exists():
        click.echo(f"✗ Database not found at {db_path}", err=True)
        sys.exit(1)

    password = get_master_password()

    try:
        db = AIModelGuardDatabase(str(db_path), password, auto_backup=True)
        results = db.backup_manager.verify_all_backups()
        db.close()

        click.echo(f"Backup Verification Report:")
        click.echo(f"  Total: {results['total']}")
        click.echo(f"  Valid: {results['valid']}")
        click.echo(f"  Invalid: {results['invalid']}")
        click.echo("")

        if results['invalid'] > 0:
            click.echo("⚠ Some backups are corrupted:")
            for detail in results['details']:
                if not detail['valid']:
                    click.echo(f"  ✗ {detail['name']}")
            sys.exit(1)
        else:
            click.echo("✓ All backups are valid")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
def handbook():
    """Print the path to the bundled operations handbook (PDF).

    The handbook is installed alongside the package via `pip install aimodelguard`
    and is also downloadable from the project's PyPI page. It contains the full
    reference documentation in a printable, shareable format.
    """
    import shutil
    from pathlib import Path

    # Try the installed location (data_files target) first
    candidates = []

    # sys.prefix/share/doc/aimodelguard/ (POSIX, set by data_files)
    if hasattr(sys, "prefix"):
        candidates.append(Path(sys.prefix) / "share" / "doc" / "aimodelguard" / "AIModelGuard-Handbook.pdf")

    # The package's own docs/ dir (when running from a source checkout or in-tree)
    pkg_dir = Path(__file__).resolve().parent.parent
    candidates.append(pkg_dir / "docs" / "AIModelGuard-Handbook.pdf")

    # Find the first one that exists
    found = None
    for path in candidates:
        if path.exists():
            found = path
            break

    if found is None:
        click.echo("✗ Handbook PDF not found.", err=True)
        click.echo("  Expected at one of:", err=True)
        for path in candidates:
            click.echo(f"    - {path}", err=True)
        click.echo("", err=True)
        click.echo("  If you installed via pip, the package data may be missing.", err=True)
        click.echo("  Try reinstalling: pip install --force-reinstall aimodelguard", err=True)
        sys.exit(1)

    click.echo(str(found))


if __name__ == "__main__":
    cli()
