"""
Optional integration with llama-cpp-python.

This is a thin wrapper that calls aimodelguard.verify() before
delegating to llama_cpp.Llama. If the model is not approved,
the wrapper raises PermissionError and the load is aborted.

Install llama-cpp-python separately:
    pip install llama-cpp-python

Usage:
    >>> from aimodelguard.integrations.llama_cpp import Llama
    >>> llm = Llama(model_path="/var/models/qwen.gguf")
"""

from pathlib import Path
from typing import Optional

import aimodelguard


def Llama(
    model_path: str,
    use_case: Optional[str] = None,
    db_path: Optional[str] = None,
    password: Optional[str] = None,
    **kwargs,
):
    """Load a GGUF model with llama-cpp-python, after verifying it with ModelGuard.

    Args:
        model_path: Path to the .gguf model file.
        use_case:   Optional use case to check (e.g., "extraction").
        db_path:    Optional path to the ModelGuard database.
        password:   Optional master password (defaults to MODELGUARD_PASSWORD env var
                    or interactive prompt).
        **kwargs:   Forwarded verbatim to llama_cpp.Llama.

    Returns:
        A llama_cpp.Llama instance.

    Raises:
        PermissionError: if the model is not approved (fail-closed).
        ImportError:     if llama-cpp-python is not installed.

    Example:
        >>> llm = Llama(model_path="/var/models/qwen.gguf", n_ctx=2048)
        >>> output = llm("Q: What is 2+2? A:", max_tokens=20)
    """
    try:
        from llama_cpp import Llama as _Llama
    except ImportError as e:
        raise ImportError(
            "llama-cpp-python is not installed. "
            "Install it with: pip install llama-cpp-python"
        ) from e

    # Verify BEFORE loading — fail closed
    result = aimodelguard.verify(
        model_path,
        use_case=use_case,
        db_path=db_path,
        password=password,
    )

    if not result.approved:
        raise PermissionError(
            f"ModelGuard denied load of {Path(model_path).name}: "
            f"{result.reason}. Approve it with "
            f"`aimodelguard approve --model {model_path}` first."
        )

    # Approved — delegate to the real loader
    return _Llama(model_path=model_path, **kwargs)
