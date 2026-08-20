#!/usr/bin/env python3
"""Shared plumbing for the Day 20 lab.

Boring on purpose: path resolution, JSON manifests, hardware defaults, locating
the llama.cpp binaries, and starting/stopping a server. The interesting parts of
the lab -- sweep grids, llama-bench flags, prompt sets, metric choices -- stay
visible in each track's own script.

Every track imports this the same way:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
    import labkit
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

# Ensure UTF-8 output on Windows consoles to prevent cp1258/cp1252 UnicodeEncodeError
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Pinned llama.cpp release. Gemma 4 (architecture "gemma4", April 2026) needs a
# build newer than that; this one is well past it. Bump deliberately, not casually.
LLAMA_CPP_BUILD = "b10488"

# ── Model registry ────────────────────────────────────────────
# Two options. Gemma 4 E2B is the default; Qwen3.5 0.8B is the small path for
# laptops that cannot hold ~4 GB of weights, or for anyone who wants the whole
# lab to run in a fraction of the time. Pick one with LAB_MODEL=<key>.
MODELS: dict[str, dict] = {
    "gemma4-e2b": {
        "label": "Gemma 4 E2B",
        "repo": "unsloth/gemma-4-E2B-it-GGUF",
        "primary": ("UD-Q4_K_XL", "gemma-4-E2B-it-UD-Q4_K_XL.gguf", 2.97),
        "compare": ("UD-Q2_K_XL", "gemma-4-E2B-it-UD-Q2_K_XL.gguf", 2.24),
        "mtp": "mtp-gemma-4-E2B-it.gguf",              # bonus C1
        "mlx_repo": "unsloth/gemma-4-E2B-it-UD-MLX-4bit",
        "quant_ladder": ["UD-IQ2_M", "UD-IQ3_XXS", "UD-Q2_K_XL", "UD-Q3_K_XL",
                         "UD-Q4_K_XL", "UD-Q5_K_XL", "UD-Q6_K_XL", "UD-Q8_K_XL"],
        "quant_pattern": "gemma-4-E2B-it-{label}.gguf",
        "min_ram_gb": 8.0,
        "download_gb": 5.2,
    },
    "qwen35-0.8b": {
        "label": "Qwen3.5 0.8B",
        "repo": "unsloth/Qwen3.5-0.8B-GGUF",
        "primary": ("Q4_K_M", "Qwen3.5-0.8B-Q4_K_M.gguf", 0.50),
        "compare": ("UD-Q2_K_XL", "Qwen3.5-0.8B-UD-Q2_K_XL.gguf", 0.39),
        "mtp": None,                                    # no MTP head published
        "mlx_repo": "mlx-community/Qwen3.5-0.8B-4bit",
        "quant_ladder": ["UD-IQ2_XXS", "UD-IQ2_M", "UD-Q2_K_XL", "UD-Q3_K_XL",
                         "UD-Q4_K_XL", "UD-Q5_K_XL", "UD-Q6_K_XL", "UD-Q8_K_XL"],
        "quant_pattern": "Qwen3.5-0.8B-{label}.gguf",
        "min_ram_gb": 4.0,
        "download_gb": 0.9,
    },
}
DEFAULT_MODEL = "gemma4-e2b"
SMALL_MODEL = "qwen35-0.8b"


def model_key() -> str:
    """Which model this run uses.

    Order: LAB_MODEL env var, then whatever models/active.json recorded (so a
    student who ran setup once does not have to keep exporting the variable),
    then the default.
    """
    env = (os.environ.get("LAB_MODEL") or "").strip()
    if env:
        if env not in MODELS:
            die(f"LAB_MODEL='{env}' is not a known model.",
                f"Options: {', '.join(MODELS)}")
        return env
    p = active_json()
    if p.exists():
        try:
            key = json.loads(p.read_text()).get("model_key")
            if key in MODELS:
                return key
        except (ValueError, OSError):
            pass
    return DEFAULT_MODEL


def model_spec(key: str | None = None) -> dict:
    return MODELS[key or model_key()]


def model_label(key: str | None = None) -> str:
    return model_spec(key)["label"]


def model_repo(key: str | None = None) -> str:
    return model_spec(key)["repo"]


def primary_file(key: str | None = None) -> str:
    return model_spec(key)["primary"][1]


def compare_file(key: str | None = None) -> str:
    return model_spec(key)["compare"][1]


def mtp_file(key: str | None = None) -> str | None:
    return model_spec(key)["mtp"]


def mlx_repo(key: str | None = None) -> str:
    return model_spec(key)["mlx_repo"]


def min_ram_gb(key: str | None = None) -> float:
    return model_spec(key)["min_ram_gb"]


def quant_ladder(key: str | None = None) -> list[str]:
    return model_spec(key)["quant_ladder"]


def quant_filename(label: str, key: str | None = None) -> str:
    return model_spec(key)["quant_pattern"].format(label=label)


# Absolute floor across both models -- below this, use the cloud notebook.
MIN_RAM_GB = min(m["min_ram_gb"] for m in MODELS.values())

HF_HOST = "https://huggingface.co"
HF_MIRROR = "https://hf-mirror.com"   # same paths; useful when HF is blocked


def model_repo_url(mirror: bool = False, key: str | None = None) -> str:
    """Browsable page for the model repo."""
    return f"{HF_MIRROR if mirror else HF_HOST}/{model_repo(key)}"


def model_file_url(filename: str, mirror: bool = False, key: str | None = None) -> str:
    """Direct download URL for one GGUF file (what curl/wget want)."""
    host = HF_MIRROR if mirror else HF_HOST
    return f"{host}/{model_repo(key)}/resolve/main/{filename}"


# Ports are overridable because some hosts already occupy 8080 — Colab runs its own
# service there, so the cloud notebook sets LAB_SERVER_PORT.
DEFAULT_PORT = 8080          # fallback when LAB_SERVER_PORT is unset
EMBED_PORT = 8081            # fallback when LAB_EMBED_PORT is unset


def server_port() -> int:
    return env_int("LAB_SERVER_PORT", DEFAULT_PORT)


def embed_port() -> int:
    return env_int("LAB_EMBED_PORT", EMBED_PORT)


def base_url(port: int | None = None) -> str:
    return f"http://localhost:{port or server_port()}"


# ─────────────────────────────────────────────────────────── paths

def repo_root() -> Path:
    """Repo root, resolved from this file - so scripts work from any CWD."""
    return Path(__file__).resolve().parents[1]


def hardware_json() -> Path:
    return repo_root() / "hardware.json"


def active_json() -> Path:
    return repo_root() / "models" / "active.json"


def bench_dir() -> Path:
    d = repo_root() / "benchmarks"
    d.mkdir(exist_ok=True)
    return d


def runtime_dir() -> Path:
    return repo_root() / "runtime"


# ─────────────────────────────────────────────────────────── manifests

def load_hardware(required: bool = True) -> dict:
    p = hardware_json()
    if not p.exists():
        if required:
            die("hardware.json not found.", "Run: make probe")
        return {}
    return json.loads(p.read_text())


def load_active(required: bool = True) -> dict:
    p = active_json()
    if not p.exists():
        if required:
            die("models/active.json not found.", "Run: make setup")
        return {}
    return json.loads(p.read_text())


def primary_model() -> str:
    return load_active()["primary_model"]


def compare_model() -> str:
    return load_active()["compare_model"]


# ─────────────────────────────────────────────────────────── hardware defaults

def any_gpu(hw: dict | None = None) -> bool:
    hw = hw if hw is not None else load_hardware(required=False)
    backends = hw.get("gpu", {}).get("backends", {})
    return any(v for k, v in backends.items() if k != "cpu_only")


def threads(hw: dict | None = None) -> int:
    hw = hw if hw is not None else load_hardware(required=False)
    return env_int("LAB_N_THREADS", hw.get("cpu", {}).get("cores_physical") or 4)


_DEVICE_CACHE: dict[str, list[str]] = {}


def visible_devices(binary: Path | None = None) -> list[str]:
    """Accelerator devices the runtime binary can actually reach.

    hardware.json answers "which GPU is installed", which is NOT the same question
    as "can the llama.cpp build we downloaded use it". Upstream ships no Linux CUDA
    asset, so an NVIDIA box on Linux gets the Vulkan build -- and with no Vulkan ICD
    installed that build enumerates nothing and runs on CPU without complaining.
    Asking the binary is the only answer that cannot be wrong.

    Returns [] when there is no accelerator, no binary, or the probe fails.
    """
    exe = binary or runtime_bin("llama-server", required=False)
    if not exe:
        return []
    key = str(exe)
    if key in _DEVICE_CACHE:
        return _DEVICE_CACHE[key]
    devices: list[str] = []
    try:
        out = subprocess.run([str(exe), "--list-devices"], capture_output=True,
                             text=True, check=False, timeout=60)
        seen_header = False
        for line in (out.stdout + out.stderr).splitlines():
            if line.strip().startswith("Available devices:"):
                seen_header = True
                continue
            if seen_header:
                entry = line.strip()
                if not entry or entry == "(none)":
                    continue
                if not line.startswith((" ", "\t")):
                    break
                devices.append(entry)
    except (OSError, subprocess.SubprocessError):
        devices = []
    _DEVICE_CACHE[key] = devices
    return devices


def gpu_offload_is_live(hw: dict | None = None) -> tuple[bool, str]:
    """(offload_available, human explanation). Used to keep reports honest."""
    hw = hw if hw is not None else load_hardware(required=False)
    if not any_gpu(hw):
        return False, "no accelerator detected"
    devices = visible_devices()
    if devices:
        return True, devices[0]
    return False, ("an accelerator is installed but this llama.cpp build enumerates "
                   "no devices -- offload would silently run on CPU")


def n_gpu_layers(hw: dict | None = None) -> int:
    """Layers to offload. Defaults to 0 unless the runtime really sees a device.

    Reporting `ngl=99` while the binary is on CPU makes every generated benchmark
    header claim a GPU run that never happened, so the default is verified rather
    than assumed. Set LAB_N_GPU_LAYERS to override in either direction.
    """
    if (os.environ.get("LAB_N_GPU_LAYERS") or "").strip():
        return env_int("LAB_N_GPU_LAYERS", 0)
    hw = hw if hw is not None else load_hardware(required=False)
    if not any_gpu(hw):
        return 0
    return 99 if visible_devices() else 0


def n_ctx() -> int:
    return env_int("LAB_N_CTX", 2048)


def parallel_slots() -> int:
    return env_int("LAB_PARALLEL", 4)


def reasoning_mode() -> str:
    """Gemma 4 is a reasoning model: left on, it emits thinking tokens into
    `reasoning_content` and leaves `message.content` empty until it stops thinking.

    The lab defaults to OFF so that a 64-token budget returns a visible answer and
    TPOT measures answer tokens. Turn it on with LAB_REASONING=on to see what
    thinking costs -- those are decode tokens the user waits through too, which is
    the deck's section 0 latency taxonomy applied to a reasoning model.
    """
    mode = (os.environ.get("LAB_REASONING") or "off").strip().lower()
    return mode if mode in ("on", "off", "auto") else "off"


# ─────────────────────────────────────────────────────────── env knobs

def env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    try:
        return int(raw)
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw)
    except ValueError:
        return default


# ─────────────────────────────────────────────────────────── binaries

def runtime_bin(name: str, required: bool = True) -> Path | None:
    """Locate a llama.cpp binary: prebuilt runtime/ first, then a bonus source
    build, then PATH. Release archives vary in internal layout, so glob for it.
    """
    exe = f"{name}.exe" if sys.platform == "win32" else name
    for root in (runtime_dir(), repo_root() / "bonus" / "llama.cpp"):
        if root.exists():
            for cand in sorted(root.rglob(exe)):
                if cand.is_file() and os.access(cand, os.X_OK):
                    return cand
    found = shutil.which(exe)
    if found:
        return Path(found)
    if required:
        die(
            f"{name} not found.",
            "Run: make setup   (downloads the prebuilt llama.cpp release)",
            "Or build from source: make build-llama   (bonus track)",
        )
    return None


def source_build_bin(name: str) -> Path | None:
    """Only the from-source build (bonus B1 compares it against the prebuilt)."""
    exe = f"{name}.exe" if sys.platform == "win32" else name
    root = repo_root() / "bonus" / "llama.cpp"
    if not root.exists():
        return None
    for cand in sorted(root.rglob(exe)):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


# ─────────────────────────────────────────────────────────── server

def server_cmd(
    model: str,
    port: int | None = None,
    embedding: bool = False,
    extra: list[str] | None = None,
) -> list[str]:
    bin_path = runtime_bin("llama-server")
    port = port or (embed_port() if embedding else server_port())
    cmd = [
        str(bin_path),
        "-m", str(model),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-t", str(threads()),
        "-ngl", str(n_gpu_layers()),
        "--ctx-size", str(n_ctx()),
    ]
    if embedding:
        # Embedding regime: pooled single vector per input, no decode loop.
        cmd += ["--embedding", "--pooling", "mean"]
    else:
        # Continuous batching + Prometheus /metrics are core lab surface.
        cmd += ["--parallel", str(parallel_slots()), "--cont-batching", "--metrics"]
        # See reasoning_mode(): off by default so completions return visible content.
        cmd += ["--reasoning", reasoning_mode()]
    return cmd + (extra or [])


def wait_healthy(port: int | None = None, timeout: float = 180.0,
                 proc: subprocess.Popen | None = None) -> bool:
    """Poll /health until the server answers.

    Pass `proc` so a server that dies at startup ends the wait immediately instead
    of burning the full timeout — the student needs the error, not a 180s pause.
    """
    import httpx

    url = f"http://127.0.0.1:{port or server_port()}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc is not None and proc.poll() is not None:
            return False
        try:
            if httpx.get(url, timeout=2.0).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


@contextmanager
def serve_bg(model: str, port: int | None = None, embedding: bool = False, quiet: bool = True):
    """Run llama-server for the duration of a block, then shut it down.

    Lets track 01 measure real TTFT/TPOT over HTTP without asking the student to
    juggle two terminals before they have learned what a serving stack is.
    """
    port = port or (embed_port() if embedding else server_port())
    cmd = server_cmd(model, port=port, embedding=embedding)
    # Quiet means "not on the student's terminal", NOT "discarded": if the server
    # dies we have to be able to show them why. Log to a file and replay it.
    log_path = repo_root() / "benchmarks" / ".llama-server.log"
    log_path.parent.mkdir(exist_ok=True)
    log = open(log_path, "w") if quiet else None
    proc = subprocess.Popen(cmd, stdout=log or None, stderr=subprocess.STDOUT if log else None)
    try:
        if not wait_healthy(port, proc=proc):
            proc.terminate()
            if log:
                log.flush()
                log.close()
                log = None
            tail = ""
            try:
                tail = "".join(open(log_path).readlines()[-20:])
            except OSError:
                pass
            died = proc.poll() is not None
            why = (f"llama-server exited early (code {proc.returncode})." if died
                   else f"llama-server did not become healthy on :{port} within 180s.")
            die(
                why + ("\n\nLast lines of the server log:\n" + tail if tail.strip() else ""),
                f"Full log: {log_path}. To watch it live, run it in the foreground: make serve",
            )
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        if log:
            log.close()


# ─────────────────────────────────────────────────────────── llama-bench parsing

def bench_metric(output: str, metric: str) -> float:
    """Pull a tok/s number out of llama-bench's markdown table.

    metric is e.g. "tg128" (decode) or "pp512" (prefill).
    """
    import re

    m = re.search(rf"\|\s*{re.escape(metric)}\s*\|\s*([0-9.]+)\s*±", output)
    if m:
        return float(m.group(1))
    m = re.search(rf"{re.escape(metric)}[^0-9]+([0-9.]+)", output)
    return float(m.group(1)) if m else 0.0


def bench_all_pp(output: str) -> list[tuple[int, float]]:
    """Every pp<N> row, as (tokens, tok/s) - for the ctx-length sweep."""
    import re

    return [
        (int(m.group(1)), float(m.group(2)))
        for m in re.finditer(r"\|\s*pp(\d+)\s*\|\s*([0-9.]+)\s*±", output)
    ]


def run_bench(args: list[str], timeout: int = 1800) -> str:
    bin_path = runtime_bin("llama-bench")
    proc = subprocess.run(
        [str(bin_path)] + args, capture_output=True, text=True, check=False, timeout=timeout
    )
    return proc.stdout + proc.stderr


# ─────────────────────────────────────────────────────────── reports

def write_report(filename: str, markdown: str, data: object | None = None) -> Path:
    out = bench_dir() / filename
    out.write_text(markdown)
    if data is not None:
        out.with_suffix(".json").write_text(json.dumps(data, indent=2))
    return out


def md_table(headers: list[str], rows: list[list[object]], align: str = "") -> str:
    """align: one char per column - 'l' or 'r'. Defaults to right for all but col 0."""
    if not align:
        align = "l" + "r" * (len(headers) - 1)
    sep = "|" + "|".join("--:" if a == "r" else ":--" for a in align) + "|"
    out = ["| " + " | ".join(str(h) for h in headers) + " |", sep]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def die(*lines: str) -> None:
    print(f"ERROR: {lines[0]}", file=sys.stderr)
    for extra in lines[1:]:
        print(f"       {extra}", file=sys.stderr)
    sys.exit(1)


def banner(title: str) -> None:
    print(f"\n{'─' * 64}\n  {title}\n{'─' * 64}")


def host_tag() -> str:
    """Short identifier for the machine, used in report headers."""
    return f"{platform.system()}-{platform.machine()}"
