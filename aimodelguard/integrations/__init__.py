"""
Optional integrations with model loaders.

These are thin wrappers that call aimodelguard.verify() before
delegating to the real loader. They are designed to be optional
— installing aimodelguard does NOT install llama-cpp-python.
Install it separately if you want the integration.

Usage:

    from aimodelguard.integrations.llama_cpp import Llama
    llm = Llama(model_path="/var/models/qwen.gguf")  # auto-verifies
"""
