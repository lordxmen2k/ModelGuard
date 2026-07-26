"""
ModelGuard — A password-protected CLI for managing an allowlist of approved AI model signatures.

Prevent unauthorized AI models from running on your infrastructure.

Python library API (v0.2.0+):
    >>> import aimodelguard
    >>> result = aimodelguard.verify("/var/models/qwen.gguf")
    >>> if not result.approved:
    ...     raise RuntimeError(f"Model denied: {result.reason}")
    >>> # Safe to load
"""

__version__ = "0.2.0"
__author__ = "Gerald Enrique Nelson Mc Kenzie"
__license__ = "Apache-2.0"
__doi__ = "10.5281/zenodo.21578648"

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from .database import AIModelGuardDatabase


@dataclass
class VerifyResult:
    """The result of a aimodelguard.verify() call.

    Attributes:
        approved: True if the model is on the allowlist and all policy checks pass.
        reason:   One of "approved", "not_in_database", "use_case_not_allowed",
                  "expired", "quarantined", "database_not_found",
                  "file_not_found", "invalid_password", "io_error".
        sha256_hash: The SHA-256 hash of the file that was checked.
        model_name:  The basename of the model file.
        publisher:   The publisher recorded at approval time, if any.
        use_cases:   The allowed use cases, if any restrictions were set.
        details:     Free-form details dictionary for advanced callers.
    """
    approved: bool
    reason: str
    sha256_hash: Optional[str] = None
    model_name: Optional[str] = None
    publisher: Optional[str] = None
    use_cases: Optional[List[str]] = None
    details: Optional[dict] = None

    def __bool__(self) -> bool:
        """Allow `if aimodelguard.verify(path):` truthy checks."""
        return self.approved


def verify(
    model_path: str,
    use_case: Optional[str] = None,
    db_path: Optional[str] = None,
    password: Optional[str] = None,
) -> VerifyResult:
    """Verify whether a model file is approved to run.

    This is the programmatic equivalent of `aimodelguard verify --model PATH`.
    It checks the file's SHA-256 hash against the local allowlist and applies
    all policy rules (expiration, quarantine, use case restrictions).

    Args:
        model_path: Path to the model file to check. Must exist and be readable.
        use_case:   Optional. If set, the model must be approved for this
                    specific use case (e.g., "extraction", "code_generation").
        db_path:    Optional. Path to the ModelGuard database. Defaults to
                    ~/.aimodelguard/db.sqlite if not specified.
        password:   Optional. The master password. If not provided, the
                    function looks for the MODELGUARD_PASSWORD environment
                    variable, then prompts interactively.

    Returns:
        A VerifyResult with `approved=True/False` and a `reason` string.
        The function does NOT raise on denial — it returns a result object
        so callers can decide what to do.

    Raises:
        FileNotFoundError: if the model file doesn't exist AND
                          the caller passed a strict path (caught and
                          returned as a VerifyResult with approved=False).
        RuntimeError:      if the database is locked or corrupted and
                          the operation cannot complete.

    Example:
        >>> import aimodelguard
        >>> result = aimodelguard.verify("/var/models/qwen.gguf")
        >>> if result.approved:
        ...     from llama_cpp import Llama
        ...     llm = Llama(model_path="/var/models/qwen.gguf")
        ... else:
        ...     print(f"BLOCKED: {result.reason}")
    """
    import os

    model_path = str(model_path)

    # 1. File must exist
    if not Path(model_path).exists():
        return VerifyResult(
            approved=False,
            reason="file_not_found",
            model_name=Path(model_path).name,
        )

    # 2. Resolve database path
    if db_path is None:
        db_path = os.environ.get(
            "MODELGUARD_DB_PATH",
            str(Path.home() / ".aimodelguard" / "db.sqlite"),
        )

    db_path = str(Path(db_path).expanduser())

    # 3. If the database doesn't exist, the model is not approved
    if not Path(db_path).exists():
        return VerifyResult(
            approved=False,
            reason="database_not_found",
            model_name=Path(model_path).name,
            details={"db_path": db_path},
        )

    # 4. Resolve password
    if password is None:
        password = os.environ.get("MODELGUARD_PASSWORD")
    if password is None:
        # Defer to click.prompt for interactive use
        import click
        password = click.prompt("Enter master password", hide_input=True)

    # 5. Open the database and check
    try:
        db = AIModelGuardDatabase(db_path, password, auto_backup=False)
    except ValueError:
        return VerifyResult(
            approved=False,
            reason="invalid_password",
            model_name=Path(model_path).name,
        )

    try:
        result = db.verify_model(
            model_path=model_path,
            use_case=use_case,
        )

        # Map the DB result to our public result type
        if result.get("approved"):
            details = result.get("details", {})
            return VerifyResult(
                approved=True,
                reason="approved",
                sha256_hash=details.get("sha256_hash"),
                model_name=Path(model_path).name,
                publisher=details.get("publisher"),
                use_cases=details.get("use_cases"),
                details=details,
            )
        else:
            return VerifyResult(
                approved=False,
                reason=result.get("reason", "not_in_database"),
                model_name=Path(model_path).name,
                details=result,
            )
    finally:
        db.close()


__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "__doi__",
    "verify",
    "VerifyResult",
]
