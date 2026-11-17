import hashlib
import json
import sys
import types
from pathlib import Path

import pytest

from urgentdentbench.llm import FakeChatModel, LlamaCppChatModel, example_from_schema, load_chat_model
from urgentdentbench.registry import (
    FAKE_MODEL,
    ModelError,
    ModelSpec,
    default_judge,
    download_model,
    fits,
    get_model,
    load_models,
    model_path,
    verified_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
SPEC = ModelSpec(name="tiny", role="test", repo="org/tiny-GGUF", file="tiny-Q4_K_M.gguf", license="MIT",
                 size_gb=0.1, min_memory_gb=8)
WEIGHTS = b"not really a gguf file"
WEIGHTS_SHA = hashlib.sha256(WEIGHTS).hexdigest()


def fake_fetch(spec, target_dir):
    path = Path(target_dir) / spec.file
    path.write_bytes(WEIGHTS)
    return str(path)


def no_network(spec):
    raise AssertionError("should not contact Hugging Face")


# ------------------------------------------------------------------ models.yaml

def test_committed_models_file_has_one_model_per_role_and_complete_metadata():
    specs = load_models(ROOT / "models.yaml")
    roles = {spec.role for name, spec in specs.items() if name != FAKE_MODEL}
    assert roles == {"test", "evaluated", "judge"}
    for spec in specs.values():
        if not spec.is_fake:
            assert spec.repo and spec.file.endswith(".gguf") and spec.license
            assert spec.size_gb > 0 and spec.min_memory_gb > spec.size_gb


def test_committed_judges_cover_16_24_and_36_gb_macs():
    specs = load_models(ROOT / "models.yaml")
    assert default_judge(specs, 16).name == "qwen2.5-14b-q3"
    assert default_judge(specs, 24).name == "qwen2.5-14b"
    assert default_judge(specs, 48).name == "qwen2.5-32b"
    assert default_judge(specs, None).name == "qwen2.5-14b-q3"
    with pytest.raises(ModelError, match="No judge"):
        default_judge(specs, 8)


@pytest.mark.parametrize(
    "entry,message",
    [
        ({"name": "x", "role": "test"}, "missing"),
        (dict(SPEC.__dict__, role="teacher"), "role"),
        (dict(SPEC.__dict__, file="tiny.bin"), ".gguf"),
        (dict(SPEC.__dict__, colour="blue"), "unknown keys"),
        (dict(SPEC.__dict__, name="fake"), "reserved"),
    ],
)
def test_load_models_rejects_bad_entries(tmp_path, entry, message):
    path = tmp_path / "models.yaml"
    path.write_text(json.dumps({"models": [entry]}))
    with pytest.raises(ModelError, match=message):
        load_models(path)


def test_get_model_names_the_choices():
    with pytest.raises(ModelError, match="fake"):
        get_model({"fake": None}, "gpt")


def test_fits_leaves_unknown_memory_undecided():
    assert fits(SPEC, 16) is True
    assert fits(SPEC, 4) is False
    assert fits(SPEC, None) is None


# ------------------------------------------------------------------ download and verification

def test_download_fetches_verifies_and_records_the_checksum(tmp_path):
    path = download_model(SPEC, tmp_path, fetch=fake_fetch, remote_sha256=lambda spec: WEIGHTS_SHA)
    assert path == model_path(SPEC, tmp_path)
    assert json.loads((tmp_path / "checksums.json").read_text())["tiny"]["sha256"] == WEIGHTS_SHA
    assert verified_sha256(SPEC, tmp_path) == WEIGHTS_SHA


def test_download_rejects_a_file_whose_hash_differs(tmp_path):
    with pytest.raises(ModelError, match="SHA-256"):
        download_model(SPEC, tmp_path, fetch=fake_fetch, remote_sha256=lambda spec: "0" * 64)


def test_pinned_hash_needs_no_network_and_existing_files_are_not_refetched(tmp_path):
    pinned = ModelSpec(**dict(SPEC.__dict__, sha256=WEIGHTS_SHA))
    download_model(pinned, tmp_path, fetch=fake_fetch, remote_sha256=no_network)
    download_model(pinned, tmp_path, fetch=lambda *a: pytest.fail("refetched"), remote_sha256=no_network)


def test_verified_sha256_detects_a_changed_file(tmp_path):
    path = download_model(SPEC, tmp_path, fetch=fake_fetch, remote_sha256=lambda spec: WEIGHTS_SHA)
    path.write_bytes(b"tampered weights, different size")
    with pytest.raises(ModelError, match="changed"):
        verified_sha256(SPEC, tmp_path)


def test_verified_sha256_needs_a_downloaded_and_verified_file(tmp_path):
    with pytest.raises(ModelError, match="udb download"):
        verified_sha256(SPEC, tmp_path)
    model_path(SPEC, tmp_path).parent.mkdir(parents=True)
    model_path(SPEC, tmp_path).write_bytes(WEIGHTS)
    with pytest.raises(ModelError, match="not verified"):
        verified_sha256(SPEC, tmp_path)


def test_fake_model_needs_no_files(tmp_path):
    specs = load_models(ROOT / "models.yaml")
    assert verified_sha256(specs["fake"], tmp_path) == "0" * 64
    assert isinstance(load_chat_model(specs["fake"], tmp_path), FakeChatModel)
    with pytest.raises(ModelError, match="nothing to download"):
        download_model(specs["fake"], tmp_path)


# ------------------------------------------------------------------ backends

def test_example_from_schema_builds_a_minimal_valid_value():
    schema = {
        "type": "object",
        "properties": {
            "urgency": {"enum": ["emergency", "urgent"]},
            "flags": {"type": "array", "items": {"type": "integer"}},
            "ok": {"type": "boolean"},
            "note": {"type": ["null", "string"]},
            "nested": {"type": "object", "properties": {"n": {"type": "integer", "minimum": 2}}},
        },
    }
    assert example_from_schema(schema) == {"urgency": "emergency", "flags": [], "ok": False, "note": "fake",
                                           "nested": {"n": 2}}


def test_fake_model_records_calls_and_answers_json_when_asked():
    model = FakeChatModel()
    text = model.chat([{"role": "user", "content": "hi"}], temperature=0, max_tokens=5, seed=1)
    data = model.chat([], temperature=0, max_tokens=5, seed=1, json_schema={"type": "object", "properties": {
        "asks": {"type": "boolean"}}})
    assert text.startswith("FAKE RESPONSE")
    assert json.loads(data) == {"asks": False}
    assert len(model.calls) == 2 and model.calls[0]["messages"][0]["content"] == "hi"


def test_llama_backend_is_optional_and_explains_how_to_install(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "llama_cpp", None)
    with pytest.raises(ModelError, match="GGML_METAL"):
        LlamaCppChatModel(tmp_path / "m.gguf", "m")


def test_llama_backend_offloads_to_gpu_and_passes_the_json_schema(monkeypatch, tmp_path):
    created = {}

    class FakeLlama:
        def __init__(self, **kwargs):
            created.update(kwargs)

        def create_chat_completion(self, **kwargs):
            created["call"] = kwargs
            return {"choices": [{"message": {"content": "{}"}}]}

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeLlama))
    model = LlamaCppChatModel(tmp_path / "m.gguf", "m", n_ctx=4096)
    reply = model.chat([{"role": "user", "content": "x"}], temperature=0.0, max_tokens=64, seed=7,
                       json_schema={"type": "object"})
    assert reply == "{}"
    assert created["n_gpu_layers"] == -1 and created["n_ctx"] == 4096
    assert created["call"]["response_format"] == {"type": "json_object", "schema": {"type": "object"}}
    assert created["call"]["seed"] == 7 and created["call"]["temperature"] == 0.0


def test_loading_a_model_that_is_not_downloaded_fails_clearly(tmp_path):
    with pytest.raises(ModelError, match="udb download --model tiny"):
        load_chat_model(SPEC, tmp_path)
