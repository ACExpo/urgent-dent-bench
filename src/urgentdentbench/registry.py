"""Local model registry: the entries of models.yaml, memory checks, download and verification.

Model files are GGUF weights from Hugging Face stored under ``models/<name>/``.
``download_model`` fetches a file once and checks its SHA-256 against the
hash Hugging Face publishes for it; the verified hash is recorded in
``models/checksums.json`` so later runs can detect a corrupted or replaced
file without contacting the network.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

ROLES = ("test", "evaluated", "judge")
FAKE_MODEL = "fake"
CHECKSUMS = "checksums.json"
REQUIRED_KEYS = ("name", "role", "repo", "file", "license", "size_gb", "min_memory_gb")


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelSpec:
    name: str
    role: str
    repo: str
    file: str
    license: str
    size_gb: float
    min_memory_gb: float
    context: int = 8192
    revision: str = "main"
    sha256: Optional[str] = None
    notes: str = ""

    @property
    def is_fake(self):
        return self.name == FAKE_MODEL


FAKE_SPEC = ModelSpec(
    name=FAKE_MODEL, role="test", repo="(built in)", file="(none)", license="MIT", size_gb=0, min_memory_gb=0,
    notes="Offline stand-in that returns canned answers; for tests and dry runs, never for results.",
)


def load_models(path):
    """Model specs from ``path`` keyed by name, plus the built-in ``fake`` model."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    entries = data.get("models") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise ModelError(f"{path}: expected a non-empty 'models' list")
    specs = {FAKE_MODEL: FAKE_SPEC}
    for i, entry in enumerate(entries):
        spec = _parse_entry(entry, f"{path}: models[{i}]")
        if spec.name in specs:
            raise ModelError(f"{path}: model name {spec.name!r} is used twice or is reserved")
        specs[spec.name] = spec
    return specs


def _parse_entry(entry, where):
    if not isinstance(entry, dict):
        raise ModelError(f"{where}: expected a mapping")
    missing = [k for k in REQUIRED_KEYS if k not in entry]
    if missing:
        raise ModelError(f"{where}: missing {missing}")
    unknown = sorted(set(entry) - set(ModelSpec.__dataclass_fields__))
    if unknown:
        raise ModelError(f"{where}: unknown keys {unknown}")
    if entry["role"] not in ROLES:
        raise ModelError(f"{where}: role must be one of {ROLES}")
    if not str(entry["file"]).endswith(".gguf"):
        raise ModelError(f"{where}: file must be a .gguf file")
    return ModelSpec(**entry)


def get_model(specs, name):
    if name not in specs:
        raise ModelError(f"Unknown model {name!r}; models.yaml defines {sorted(specs)}")
    return specs[name]


def system_memory_gb():
    """Physical memory in GB, or None when it cannot be read."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True)
            return int(out.stdout.strip()) / 1024 ** 3
        with open("/proc/meminfo", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / 1024 ** 2
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None
    return None


def fits(spec, memory_gb):
    """Whether ``spec`` fits in ``memory_gb`` (None when the memory is unknown)."""
    if memory_gb is None:
        return None
    return spec.min_memory_gb <= memory_gb + 0.5


def default_judge(specs, memory_gb):
    """The largest judge that fits ``memory_gb``, or the smallest judge when memory is unknown."""
    judges = sorted((s for s in specs.values() if s.role == "judge"), key=lambda s: s.min_memory_gb)
    if not judges:
        raise ModelError("models.yaml defines no judge model")
    if memory_gb is None:
        return judges[0]
    fitting = [s for s in judges if fits(s, memory_gb)]
    if not fitting:
        raise ModelError(f"No judge in models.yaml fits {memory_gb:.0f} GB; pass --model explicitly")
    return fitting[-1]


def model_path(spec, models_dir):
    return Path(models_dir) / spec.name / spec.file


def sha256_file(path, chunk_size=1 << 24):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksums(models_dir):
    path = Path(models_dir) / CHECKSUMS
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write_checksum(spec, models_dir, path, sha256):
    records = _read_checksums(models_dir)
    stat = path.stat()
    records[spec.name] = {"file": spec.file, "sha256": sha256, "size": stat.st_size, "mtime": stat.st_mtime}
    (Path(models_dir) / CHECKSUMS).write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _hf_fetch(spec, target_dir):
    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise ModelError(_install_hint("huggingface_hub")) from exc
    return hf_hub_download(repo_id=spec.repo, filename=spec.file, revision=spec.revision, local_dir=target_dir)


def _hf_remote_sha256(spec):
    try:
        from huggingface_hub import HfApi
    except ImportError as exc:
        raise ModelError(_install_hint("huggingface_hub")) from exc
    infos = HfApi().get_paths_info(spec.repo, [spec.file], revision=spec.revision)
    if not infos:
        raise ModelError(f"{spec.repo} has no file {spec.file}")
    lfs = getattr(infos[0], "lfs", None)
    sha256 = getattr(lfs, "sha256", None) or (lfs.get("sha256") if isinstance(lfs, dict) else None)
    if not sha256:
        raise ModelError(f"Hugging Face publishes no SHA-256 for {spec.repo}/{spec.file}")
    return sha256


def _install_hint(package):
    return (f"{package} is not installed. Install the local-model extras: "
            "CMAKE_ARGS=\"-DGGML_METAL=on\" pip install -e \".[local]\"")


def download_model(spec, models_dir, fetch=_hf_fetch, remote_sha256=_hf_remote_sha256):
    """Download ``spec`` into ``models_dir`` if needed, verify it, and return its path."""
    if spec.is_fake:
        raise ModelError("The fake model has nothing to download")
    path = model_path(spec, models_dir)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        fetched = Path(fetch(spec, path.parent))
        if fetched.resolve() != path.resolve():
            raise ModelError(f"Downloaded {fetched}, expected {path}")
    expected = spec.sha256 or remote_sha256(spec)
    actual = sha256_file(path)
    if actual != expected:
        raise ModelError(f"{path} does not match its published SHA-256 ({actual} != {expected}); "
                         "delete it and download again")
    _write_checksum(spec, models_dir, path, actual)
    return path


def verified_sha256(spec, models_dir):
    """SHA-256 of a downloaded model, checked against the one recorded at download.

    The file is only re-hashed when its size or modification time changed.
    """
    if spec.is_fake:
        return "0" * 64
    path = model_path(spec, models_dir)
    if not path.exists():
        raise ModelError(f"{spec.name} is not downloaded; run: udb download --model {spec.name}")
    record = _read_checksums(models_dir).get(spec.name)
    if record is None or record.get("file") != spec.file:
        raise ModelError(f"{spec.name} was not verified; run: udb download --model {spec.name}")
    stat = path.stat()
    if stat.st_size == record["size"] and stat.st_mtime == record["mtime"]:
        return record["sha256"]
    actual = sha256_file(path)
    if actual != record["sha256"]:
        raise ModelError(f"{path} changed since it was verified; run: udb download --model {spec.name}")
    _write_checksum(spec, models_dir, path, actual)
    return actual
