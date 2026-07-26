# Changelog

All notable changes to AI Model Guard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**DOI:** [10.5281/zenodo.21578648](https://doi.org/10.5281/zenodo.21578648)

## [Unreleased]

Nothing planned. AI Model Guard v0.2.0 is the last planned release. Future work is "use the tool, report bugs".

## [0.2.0] - 2026-07-25

### Added
- **Python library API** — `import aimodelguard; aimodelguard.verify(path)` returns a `VerifyResult` dataclass
  - `result.approved` is a bool
  - `result.reason` is one of: `approved`, `not_in_database`, `quarantined`, `expired`, `use_case_not_allowed`, `file_not_found`, `database_not_found`, `invalid_password`
  - `result.sha256_hash`, `result.publisher`, `result.use_cases`, `result.details` for advanced use
  - `bool(result)` is equivalent to `result.approved`, so `if aimodelguard.verify(path):` works
  - Password resolution: `password=` arg → `MODELGUARD_PASSWORD` env var → `click.prompt` (in that order)
- **`aimodelguard.integrations.llama_cpp`** — thin wrapper that verifies a model with `aimodelguard.verify()` and then loads it with `llama-cpp-python`. Raises `PermissionError` on denial.
  - `pip install llama-cpp-python` separately to enable (not a required dependency)
- **`database.verify_model()` result now includes `sha256_hash`** in the details dict
- **13 new tests** in `tests/test_library_api.py` — covers all result types, password sources, use case policy, quarantine, env var fallback
- **Total test count:** 20 (was 7 in v0.1.0)
- **`aimodelguard handbook` command** — prints the path to the bundled operations handbook PDF
- **Handbook PDF bundled with the package** — `docs/AIModelGuard-Handbook.pdf` is installed alongside the code (under `share/doc/aimodelguard/` on POSIX systems), making the full reference documentation available to anyone who runs `pip install aimodelguard`. No separate download needed.

### Changed
- Version bumped to 0.2.0 in `setup.py`, `pyproject.toml`, and `aimodelguard/__init__.py`
- README adds a "Python Library API" section under Quick Start with usage example

### Design constraints (still enforced)
- No new CLI commands, no new policy, no new dependencies
- No network calls, no transparency logs, no publisher signatures
- The library API is a thin wrapper around the same logic the CLI uses — no parallel code paths

## [0.1.0] - 2026-07-23

### Added
- Initial alpha release
- Password-protected SQLite database with PBKDF2 key derivation
- SHA-256 model hash verification
- CLI commands:
  - `aimodelguard init` — Initialize the database
  - `aimodelguard approve` — Approve a model with optional use case restrictions and expiration
  - `aimodelguard verify` — Verify if a model is approved (with JSON output for scripts)
  - `aimodelguard list` — List all approved models
  - `aimodelguard remove` — Remove a model from the approved list
  - `aimodelguard quarantine` — Quarantine a model (block from running)
  - `aimodelguard audit` — View the audit log
  - `aimodelguard backup create/list/restore/verify` — Database backup management
- Automatic backups before destructive operations (remove, quarantine)
- Manual backup creation with labels
- Backup restoration with safety backup
- Backup integrity verification
- Audit logging for all operations (approve, verify, remove, quarantine)
- Use case restrictions (models can be approved for specific purposes)
- Expiration dates (models can be set to expire after N days)
- Trust levels (verified, community, experimental)
- Configurable backup retention (default: keep last 10 backups)
- Comprehensive test suite (6 tests, all passing)
- Apache 2.0 license
- Full documentation (README.md, PUBLISH.md)
- **`MODELGUARD_PASSWORD` environment variable** for non-interactive password input (great for CI/scripts)
- Password prompt uses `click.prompt(hide_input=True)` for cross-platform TTY handling (Linux, macOS, Windows)

### Security
- Master password hashing with PBKDF2-HMAC-SHA256 (100,000 iterations)
- Random salt generation for each database
- File permissions set to 0o600 for database and salt files
- Password verification via sentinel value in database
- Automatic backups prevent data loss from accidental destructive operations
- **Zero external dependencies at runtime** — no network calls, no phone-home, no cloud sync, works fully air-gapped
- **Hash-only verification** — format-agnostic (GGUF, safetensors, PyTorch, ONNX, anything); does not parse or load model contents
- **Fail-closed by default** — unverified loads are blocked, not warned about

### Known Limitations
- Database is not encrypted at rest (uses SQLite, not SQLCipher)
- No multi-user support (single master password)
- No remote/centralized management
- No two-person approval workflow
- No publisher signature verification (only SHA-256 hashing)
- No integration with specific model loaders (llama.cpp, Hugging Face, etc.)
- `MODELGUARD_PASSWORD` env var is convenient but visible to any process that can read the environment (e.g., `/proc/<pid>/environ` on Linux, or `Get-Process` env in PowerShell). For production, prefer the interactive prompt or a secrets manager that injects the env var only for the duration of the command.
