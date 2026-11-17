"""Chat backends: local GGUF models through llama.cpp, and an offline fake for tests.

Every backend exposes ``chat(messages, *, temperature, max_tokens, seed,
json_schema=None) -> str``. With ``json_schema`` the reply is constrained to
JSON matching the schema (llama.cpp turns the schema into a grammar).
"""
from __future__ import annotations

import json

from .registry import ModelError, model_path


class LlamaCppChatModel:
    """A GGUF model run locally by llama-cpp-python, fully offloaded to the GPU (Metal on Apple Silicon)."""

    def __init__(self, path, name, n_ctx=8192, n_gpu_layers=-1, verbose=False):
        try:
            from llama_cpp import Llama
        except ImportError as exc:
            raise ModelError(
                "llama-cpp-python is not installed. On Apple Silicon install it with Metal: "
                "CMAKE_ARGS=\"-DGGML_METAL=on\" pip install -e \".[local]\""
            ) from exc
        self.name = name
        self._llm = Llama(model_path=str(path), n_ctx=n_ctx, n_gpu_layers=n_gpu_layers, verbose=verbose)

    def chat(self, messages, *, temperature, max_tokens, seed, json_schema=None):
        kwargs = {"messages": messages, "temperature": temperature, "max_tokens": max_tokens, "seed": seed}
        if json_schema is not None:
            kwargs["response_format"] = {"type": "json_object", "schema": json_schema}
        completion = self._llm.create_chat_completion(**kwargs)
        return completion["choices"][0]["message"]["content"] or ""


def example_from_schema(schema):
    """A minimal value that satisfies ``schema`` (the subset of JSON Schema udb uses)."""
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = next((k for k in kind if k != "null"), "null")
    if kind == "object":
        return {key: example_from_schema(sub) for key, sub in schema.get("properties", {}).items()}
    if kind == "array":
        return [example_from_schema(schema.get("items", {})) for _ in range(schema.get("minItems", 0))]
    defaults = {"string": "fake", "boolean": False, "integer": schema.get("minimum", 0), "number": 0.0, "null": None}
    return defaults.get(kind)


def default_fake_reply(messages, json_schema):
    if json_schema is not None:
        return json.dumps(example_from_schema(json_schema))
    return "FAKE RESPONSE: canned answer from the offline test model."


class FakeChatModel:
    """Deterministic offline model: never downloads or loads weights.

    ``reply(messages, json_schema)`` produces each answer; the default returns
    a fixed sentence, or the minimal JSON object for a schema. Every call is
    kept in ``calls`` so tests can inspect the prompts.
    """

    def __init__(self, reply=default_fake_reply, name="fake"):
        self.name = name
        self.reply = reply
        self.calls = []

    def chat(self, messages, *, temperature, max_tokens, seed, json_schema=None):
        self.calls.append({"messages": [dict(m) for m in messages], "temperature": temperature,
                           "max_tokens": max_tokens, "seed": seed, "json_schema": json_schema})
        return self.reply(messages, json_schema)


def load_chat_model(spec, models_dir, n_ctx=None):
    """The chat backend for ``spec``: the fake model, or a downloaded GGUF file."""
    if spec.is_fake:
        return FakeChatModel()
    path = model_path(spec, models_dir)
    if not path.exists():
        raise ModelError(f"{spec.name} is not downloaded; run: udb download --model {spec.name}")
    return LlamaCppChatModel(path, spec.name, n_ctx=n_ctx or spec.context)
