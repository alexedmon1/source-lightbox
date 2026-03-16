"""Generate JPEG thumbnails from PNG figures using Pillow."""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


def _generate_one(src: Path, dst: Path, size: int, quality: int) -> str:
    """Generate a single thumbnail. Returns dst path on success, error string on failure."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size), Image.LANCZOS)
            img.save(dst, "JPEG", quality=quality, optimize=True)
        return str(dst)
    except Exception as e:
        return f"ERROR: {src} -> {e}"


def generate_thumbnails(
    tasks: list[tuple[Path, Path]],
    size: int = 300,
    quality: int = 80,
    workers: int = 4,
    on_progress: callable = None,
) -> list[str]:
    """Generate thumbnails in parallel.

    Args:
        tasks: List of (src_path, dst_path) tuples.
        size: Max dimension for thumbnails.
        quality: JPEG quality (1-100).
        workers: Number of parallel workers.
        on_progress: Optional callback(completed, total).

    Returns:
        List of error messages (empty if all succeeded).
    """
    errors = []
    total = len(tasks)
    completed = 0

    # Skip tasks where thumbnail already exists and is newer than source
    filtered = []
    for src, dst in tasks:
        if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
            completed += 1
            continue
        filtered.append((src, dst))

    if not filtered:
        return errors

    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_generate_one, src, dst, size, quality): (src, dst)
            for src, dst in filtered
        }
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            if result.startswith("ERROR:"):
                errors.append(result)
            if on_progress:
                on_progress(completed, total)

    return errors
