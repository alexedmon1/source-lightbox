"""Per-subject QC metadata (treatment group + outlier flags) for the browser.

Outlier detection mirrors ``source_localization.study.qc.detect_outliers`` — the
same four metrics, sample-std z-score, and 2.0 threshold — so the lightbox's
flags agree with the QC report it sits next to.
"""

from __future__ import annotations

# Mirror source_localization.study.qc.detect_outliers.
_OUTLIER_METRICS = ("forward_condition_number", "stc_amp_mean", "stc_amp_max", "stc_n_times")
_THRESHOLD = 2.0


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_subject_meta(qc_metrics, subject_keys, threshold: float = _THRESHOLD) -> dict:
    """Return ``{subject_key: {"group": str|None, "outliers": [metric, ...]}}``.

    Args:
        qc_metrics: list of QC row dicts (numeric ``subject_id``, ``group``, metrics).
        subject_keys: localization subject keys like ``"sub-933"`` or
            ``"sub-933_ses-01"`` (the source-localization ``output_id``).
        threshold: z-score cutoff (default 2.0).
    """
    meta = {key: {"group": None, "outliers": []} for key in subject_keys}
    if not qc_metrics:
        return meta

    by_id = {
        str(r.get("subject_id")): {"group": r.get("group"), "outliers": []}
        for r in qc_metrics
    }

    for col in _OUTLIER_METRICS:
        pairs = [(str(r.get("subject_id")), _to_float(r.get(col))) for r in qc_metrics]
        nums = [v for _, v in pairs if v is not None]
        if len(nums) < 2:
            continue
        mean = sum(nums) / len(nums)
        # sample std (ddof=1), matching pandas Series.std()
        std = (sum((v - mean) ** 2 for v in nums) / (len(nums) - 1)) ** 0.5
        if std == 0:
            continue
        for sid, v in pairs:
            if v is not None and abs((v - mean) / std) > threshold:
                by_id[sid]["outliers"].append(col)

    for key in subject_keys:
        sid = _qc_subject_id(key, by_id)
        if sid is not None:
            meta[key] = by_id[sid]
    return meta


def _qc_subject_id(key: str, by_id: dict) -> str | None:
    """Map a localization folder key to the QC row's ``subject_id``.

    Folders are named by ``output_id`` — ``sub-<id>`` plus optional
    ``_ses-<session>`` / ``_rec-<recording>`` suffixes — while the QC CSV
    carries the bare ``subject_id``. Try the most specific form first so a
    QC table keyed by the full output id still matches.
    """
    candidates = [key]
    bare = key[4:] if key.startswith("sub-") else key
    candidates.append(bare)
    for marker in ("_ses-", "_rec-"):
        if marker in bare:
            bare = bare.split(marker, 1)[0]
            candidates.append(bare)
    for c in candidates:
        if c in by_id:
            return c
    return None
