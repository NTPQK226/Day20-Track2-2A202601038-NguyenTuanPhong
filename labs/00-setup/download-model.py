#!/usr/bin/env python3
"""Download the lab model, two quantizations of it.

Two options, chosen with LAB_MODEL:
    LAB_MODEL=gemma4-e2b   Gemma 4 E2B    ~5.2 GB   (default, needs 8 GB RAM)
    LAB_MODEL=qwen35-0.8b  Qwen3.5 0.8B   ~0.9 GB   (small path, needs 4 GB RAM)


One model for the whole lab. Two quantizations because the quantization
comparison (deck section 1) needs a before/after on the same weights:

    primary  gemma-4-E2B-it-UD-Q4_K_XL.gguf   ~3.2 GB   the default
    compare  gemma-4-E2B-it-UD-Q2_K_XL.gguf   ~2.4 GB   the contrast

Unsloth's UD ("Unsloth Dynamic") quants keep the sensitive layers at higher
precision, so UD-Q2_K_XL is far more usable than a flat Q2_K -- which is exactly
what makes the comparison interesting rather than a foregone conclusion.

    .venv/bin/python labs/00-setup/download-model.py                # both quants
    .venv/bin/python labs/00-setup/download-model.py --with-mtp     # + MTP head (bonus C1)
    .venv/bin/python labs/00-setup/download-model.py --skip-download  # manifest only
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "lib"))
import labkit  # noqa: E402
import os

# Ensure all huggingface downloads/caches stay inside the repo on drive D
hf_cache = labkit.repo_root() / ".hf_cache"
os.environ["HF_HOME"] = str(hf_cache)
os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)


def find_local(models_dir: pathlib.Path, filename: str) -> pathlib.Path | None:
    for p in models_dir.rglob(filename):
        if p.is_file():
            return p
    return None


def fetch(repo_id: str, filename: str, models_dir: pathlib.Path) -> pathlib.Path:
    from huggingface_hub import hf_hub_download

    existing = find_local(models_dir, filename)
    if existing:
        print(f"    already present: {existing.relative_to(labkit.repo_root())}")
        return existing
    print(f"==> Downloading {filename}")
    print(f"    {labkit.model_file_url(filename)}")
    return pathlib.Path(
        hf_hub_download(repo_id=repo_id, filename=filename, local_dir=str(models_dir))
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the Gemma 4 E2B GGUFs for the lab.")
    ap.add_argument("--skip-download", action="store_true",
                    help="Locate already-downloaded files and write the manifest only")
    ap.add_argument("--with-mtp", action="store_true",
                    help="Also fetch the MTP head (~98 MB) for bonus C1 speculative decoding")
    args = ap.parse_args()

    models_dir = labkit.repo_root() / "models"
    models_dir.mkdir(exist_ok=True)
    key = labkit.model_key()
    spec = labkit.model_spec(key)
    repo = spec["repo"]

    print(f"==> Model: {spec['label']}  (LAB_MODEL={key})")
    print(f"    {labkit.model_repo_url(key=key)}")
    print("    Apache-2.0, not gated — no token, no license click-through.")
    print(f"    Download size: ~{spec['download_gb']} GB")
    other = next(k for k in labkit.MODELS if k != key)
    print(f"    (other option: LAB_MODEL={other} -> {labkit.MODELS[other]['label']}, "
          f"~{labkit.MODELS[other]['download_gb']} GB)")

    wanted = [labkit.primary_file(key), labkit.compare_file(key)]
    if args.with_mtp:
        mtp = labkit.mtp_file(key)
        if mtp:
            wanted.append(mtp)
        else:
            print(f"    (--with-mtp ignored: {spec['label']} publishes no MTP head)")

    resolved: dict[str, pathlib.Path] = {}
    if args.skip_download:
        for f in wanted:
            found = find_local(models_dir, f)
            if not found:
                labkit.die(
                    f"--skip-download but {f} is not under models/.",
                    "Drop it in manually first -- see labs/00-setup/MANUAL-DOWNLOAD.md",
                )
            print(f"==> Found {found.relative_to(labkit.repo_root())}")
            resolved[f] = found
    else:
        try:
            for f in wanted:
                resolved[f] = fetch(repo, f, models_dir)
        except ImportError:
            labkit.die("huggingface_hub not installed.", "Run: make setup")
        except Exception as exc:  # noqa: BLE001 -- surface the real cause to the student
            print(f"\nERROR: download failed: {exc}", file=sys.stderr)
            print("\nGrab the files by hand instead — either in a browser:", file=sys.stderr)
            print(f"  {labkit.model_repo_url(key=key)}/tree/main", file=sys.stderr)
            print("\nor on the command line:", file=sys.stderr)
            for f in wanted:
                print(f"  curl -L -o models/{f} \\\n    {labkit.model_file_url(f, key=key)}",
                      file=sys.stderr)
            print("\nIf Hugging Face is blocked entirely, the same paths work on the mirror:",
                  file=sys.stderr)
            print(f"  {labkit.model_file_url(wanted[0], mirror=True, key=key)}", file=sys.stderr)
            print("\nThen write the manifest:", file=sys.stderr)
            print(f"  {sys.executable} labs/00-setup/download-model.py --skip-download",
                  file=sys.stderr)
            print("\nFull instructions: labs/00-setup/MANUAL-DOWNLOAD.md", file=sys.stderr)
            return 1

    def rel(p: pathlib.Path) -> str:
        try:
            return str(p.resolve().relative_to(labkit.repo_root()))
        except ValueError:
            return str(p.resolve())

    manifest = {
        "model_key": key,
        "model": spec["label"],
        "repo_id": repo,
        "primary_model": rel(resolved[labkit.primary_file(key)]),
        "primary_quant": spec["primary"][0],
        "compare_model": rel(resolved[labkit.compare_file(key)]),
        "compare_quant": spec["compare"][0],
        "mtp_head": (rel(resolved[labkit.mtp_file(key)])
                     if args.with_mtp and labkit.mtp_file(key) in resolved else None),
        "mlx_repo": spec["mlx_repo"],
    }
    labkit.active_json().parent.mkdir(exist_ok=True)
    labkit.active_json().write_text(json.dumps(manifest, indent=2))

    total_gb = sum(p.stat().st_size for p in resolved.values()) / 1024**3
    print(f"\n==> Wrote models/active.json  ({total_gb:.1f} GB on disk)")
    for f, p in resolved.items():
        print(f"    {p.stat().st_size / 1024**3:5.2f} GB  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
