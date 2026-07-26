# AI Model Guard

**A password-protected CLI for managing an allowlist of approved AI model signatures.**

Prevent unauthorized AI models from running on your infrastructure. Only models in your approved database can execute. Every action is logged for compliance.

## Why AI Model Guard?

When you deploy AI locally, you face a trust problem:
- How do you know a model is what it claims to be?
- How do you prevent unauthorized models from running?
- How do you audit which models are in use?
- How do you respond to a compromised model?

AI Model Guard solves this with cryptographic signature verification and a local allowlist.

## Quick Start

```bash
# Install from PyPI
pip install aimodelguard

# Get the path to the bundled operations handbook (PDF)
aimodelguard handbook

# Initialize the database (one-time)
aimodelguard init

# Approve a model
aimodelguard approve --model ./qwen-1.5b.gguf --publisher "Qwen Team" --use-case "extraction"

# Verify a model before running
aimodelguard verify --model ./qwen-1.5b.gguf
```

## The Operations Handbook

The full reference documentation is shipped as a PDF alongside the code on PyPI. After `pip install aimodelguard`, run:

```bash
aimodelguard handbook
# prints the path to the bundled PDF, e.g.:
# /usr/local/share/doc/aimodelguard/AIModelGuard-Handbook.pdf
```

The PDF is 14 pages, ~870 KB, and covers everything in this README plus the threat model, security architecture, integration patterns, and troubleshooting.

**DOI:** 10.5281/zenodo.21578648 (cites the whole project: code + handbook)

## Python Library API (v0.2.0+)

For load-time checks in Python applications, use the library:

```python
import aimodelguard

result = aimodelguard.verify("/var/models/qwen.gguf")

if not result.approved:
    raise RuntimeError(f"Model denied: {result.reason}")

# result.approved       -> bool
# result.reason         -> "approved" | "not_in_database" | "quarantined" | ...
# result.sha256_hash    -> str | None
# result.publisher      -> str | None
# result.use_cases      -> list[str] | None
# bool(result)          -> same as result.approved

# Optional: load with llama-cpp-python after verifying
from aimodelguard.integrations.llama_cpp import Llama
llm = Llama(model_path="/var/models/qwen.gguf", n_ctx=2048)
```

The library accepts the same password sources as the CLI: the `password=` argument, the `MODELGUARD_PASSWORD` env var, or an interactive `click.prompt` fallback.

## Features

- **Password-protected database** — Only authorized admins can approve/remove models
- **SHA-256 model verification** — Cryptographic hashes prevent tampered models
- **Automatic backups** — Database backups before destructive operations
- **Audit logging** — Every action logged with timestamp, user, and result
- **Use case restrictions** — Models can be approved for specific purposes only
- **Expiration dates** — Models must be re-approved periodically
- **Quarantine system** — Immediately block compromised models
- **Backup management** — Manual backup creation, listing, restoration, and verification

## Commands

### Setup
- `aimodelguard init` — Initialize the database

### Model Management
- `aimodelguard approve --model PATH` — Approve a model
- `aimodelguard verify --model PATH` — Verify a model is approved
- `aimodelguard list` — List all approved models
- `aimodelguard remove --hash HASH` — Remove an approval
- `aimodelguard quarantine --model PATH` — Quarantine a model

### Backup Management
- `aimodelguard backup create` — Create a manual backup
- `aimodelguard backup list` — List all backups
- `aimodelguard backup restore PATH` — Restore from a backup
- `aimodelguard backup verify` — Verify all backups

### Compliance
- `aimodelguard audit` — View the audit log

## Use Cases

### For Security Teams
- Prevent unauthorized AI models from running on company infrastructure
- Audit which models are in use across the organization
- Respond quickly to compromised models (quarantine)
- Enforce model approval policies

### For Regulated Industries
- HIPAA compliance: Ensure only approved models process patient data
- SOX compliance: Audit trail of model usage
- FedRAMP compliance: Cryptographic verification of model integrity

### For AI/ML Teams
- Prevent "shadow AI" — models deployed without approval
- Test models safely with automatic blocking if compromised
- Roll back model approvals if issues are discovered

## Architecture

- **Python 3.11+** — Modern Python with type hints
- **SQLite** — Embedded database (no server required)
- **Click** — Command-line interface framework
- **Cryptography** — SHA-256 hashing, key derivation

## Security Model

### Design Principles

1. **Zero external dependencies at runtime** — AI Model Guard does not phone home, does not require an internet connection, and does not depend on any third-party service. The database, the hashes, and the audit log all live on your filesystem. The CLI is fully usable on an air-gapped machine.

2. **Hash-only verification** — AI Model Guard verifies cryptographic hashes (SHA-256) of model files. It does not parse model formats, does not load model weights, and does not care about file contents beyond the bytes that get hashed. This makes it format-agnostic (works with GGUF, safetensors, PyTorch, ONNX, anything else) and means a "fake" test model with random bytes is just as valid a test case as a real 7B parameter network.

3. **Fail closed** — If AI Model Guard can't verify a model (file missing, hash mismatch, expired approval, quarantined, database locked, etc.), the default behavior is to block the load. The verifier is meant to be a hard gate, not a soft suggestion.

4. **Local-first is a feature, not a limitation** — The lack of cloud sync, central management, or real-time publisher verification is a deliberate design choice. AI Model Guard's threat model is "an attacker swaps a model file on your disk" — defending against that does not require a network. If you need publisher signature verification, transparency logs, or centralized approval workflows, layer those on top of AI Model Guard; don't replace it.

5. **Simple and audit-compliant, not fool-proof** — AI Model Guard is meant to be a small, well-understood tool that you can read end-to-end, audit, and trust. The design intentionally avoids features that add complexity without a proportional security benefit: no two-person approval workflow, no transparency log, no TPM binding, no keyserver, no revocation service, no DRM. If a security team needs those, they should use a heavier tool — AI Model Guard's job is to catch the common case (file substitution) and provide a clean audit trail.

### What AI Model Guard Protects Against

✅ **Supply chain attacks** — Tampered models are rejected
✅ **Insider threats** — Unauthorized models are blocked
✅ **Compromised models** — Can be quarantined immediately
✅ **Misuse** — Use case restrictions prevent off-label use
✅ **Compliance violations** — Full audit trail

### What AI Model Guard Does NOT Protect Against

❌ **Initial model trust** — The first time you approve a model, you trust the publisher
❌ **Zero-day vulnerabilities** — AI Model Guard can't detect unknown backdoors
❌ **Bypass attacks** — Determined attackers could modify AI Model Guard itself
❌ **Password compromise** — If the master password is stolen, all bets are off

## License

Apache 2.0

## Author

Gerald Enrique Nelson Mc Kenzie

## DOI

10.5281/zenodo.21578648

## Version

0.2.0 (final — no further versions planned)

## Password Input

Every AI Model Guard command (except `init`) requires the master password. AI Model Guard provides three ways to provide it, in priority order:

### 1. `MODELGUARD_PASSWORD` environment variable (recommended for scripts/CI)

```bash
# Linux / macOS
export MODELGUARD_PASSWORD="mySecret123"
aimodelguard init --db-path ./db.sqlite
aimodelguard approve --model ./qwen-1.5b.gguf

# Windows PowerShell
$env:MODELGUARD_PASSWORD = "mySecret123"
python -m aimodelguard.cli init --db-path .\db.sqlite

# Windows cmd.exe
set MODELGUARD_PASSWORD=mySecret123
python -m aimodelguard.cli init --db-path .\db.sqlite
```

If the env var is set, the CLI uses it and never prompts. This is the recommended way to use AI Model Guard in automation, CI pipelines, and shell scripts.

### 2. Interactive prompt (default for humans)

If `MODELGUARD_PASSWORD` is not set, the CLI prompts for the password with hidden input (no echo to terminal).

```bash
aimodelguard init --db-path ./db.sqlite
# Enter master password: ********
# Confirm master password: ********
```

The prompt uses `click.prompt(hide_input=True)`, which correctly handles TTY detection on Linux, macOS, and Windows.

### 3. `init` requires confirmation

The `init` command asks for the password twice (with confirmation) to prevent typos. All other commands only ask once.

## Testing

AI Model Guard ships with a pytest test suite covering both unit-level logic and end-to-end CLI workflows.

### Running the tests

```bash
# Install with test dependencies
pip install -e ".[test]"

# Run all tests
pytest tests/ -v

# Run only the unit tests (fast)
pytest tests/test_basic.py -v

# Run only the CLI workflow tests (slower, exercises the full CLI)
pytest tests/test_cli_workflow.py -v
```

### Test password

The CLI workflow test (`tests/test_cli_workflow.py`) sets a hardcoded master password so the test can run non-interactively:

- **Test password:** `test_password_123`
- **Used in:** every `subprocess.run(...)` call inside the test that invokes a password-protected command
- **Why hardcoded:** so the test can pipe the password to `getpass` via stdin without a human typing it
- **Where it lives:** the test's `run_modelguard()` helper feeds `"test_password_123\n"` as `input_text`

This password is **only used inside the test suite** and never appears in production code paths. When you run the CLI manually, you choose your own password during `aimodelguard init`.

**How the test provides the password:** the test's `run_modelguard()` helper sets `MODELGUARD_PASSWORD=test_password_123` in the subprocess environment, which the CLI picks up and uses instead of prompting. (Previously the test piped the password via stdin, but `click.prompt(hide_input=True)` doesn't read from non-TTY stdin, so we switched to the env var.)

### What's covered

**`tests/test_basic.py`** — 6 unit tests:
- `test_compute_file_hash` — SHA-256 hashing works on real files
- `test_database_init_and_approve` — DB init, password setup, model approval
- `test_backup_and_restore` — Backup creation, listing, restoration
- `test_quarantine` — Quarantine blocks verification
- `test_audit_log` — Every action is logged with timestamp
- `test_password_verification` — Wrong password is rejected (with Windows file-lock safe cleanup)

**`tests/test_cli_workflow.py`** — 1 end-to-end test (21 scenarios):
- Create fake model files
- Initialize database with master password
- Approve / list / verify / remove / quarantine models
- Test use case restrictions (allowed vs denied)
- Create / list / verify / restore backups
- View audit log
- Negative tests (wrong password, missing files)

### Manual testing (interactive)

If you want to drive the CLI yourself:

```bash
# 1. Initialize (you'll be asked for a password)
aimodelguard init --db-path ./test.sqlite

# 2. Create a dummy model
dd if=/dev/urandom of=mymodel.gguf bs=1M count=10  # Linux/macOS
# or
fsutil file createnew mymodel.gguf 10485760         # Windows

# 3. Approve it (enter the same password)
aimodelguard approve --db-path ./test.sqlite --model ./mymodel.gguf

# 4. Verify
aimodelguard verify --db-path ./test.sqlite --model ./mymodel.gguf

# 5. List
aimodelguard list --db-path ./test.sqlite

# 6. Cleanup
rm -rf ./test.sqlite ./backups/
```

**Note on Windows:** if `aimodelguard` is not on your PATH after `pip install -e .`, use `python -m aimodelguard.cli ...` instead. The tests use this form for cross-platform compatibility.
