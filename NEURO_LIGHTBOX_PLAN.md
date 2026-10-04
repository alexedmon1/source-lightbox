# neuro-lightbox — pointer

neuro-lightbox is a separate project: **https://github.com/alexedmon1/neuro-lightbox**
(locally `~/sandbox/neuro-lightbox`), created 2026-10-02 from this repository's
history. Its plan — `NEURO_LIGHTBOX_PLAN.md` in that repository — is the live
one; this file only points there.

**Decision (author, 2026-10-04):** neuro-lightbox is for **MRI** (neurofaune
outputs); **source-lightbox stays the EEG tool** (source-analytics outputs), is
not frozen, and is developed on its own. Reason: the data are completely
different between the two modalities.

For this repository that means:

- The reporting defects that the shared code carried are to-dos here, in
  `DESIGN_NOTES.md` → "Reporting defects found 2026-10-02".
- neuro-lightbox already fixed them for EEG before the split (its commit
  `1500523`: `contract.py`, `profiles/eeg/reading.py`), so that commit is the
  implementation to port from.
- neuro-lightbox drops its `source-lightbox` command alias and `source_lightbox`
  shim in its split, so the two tools install side by side without shadowing
  each other.

Earlier versions of this file (2026-10-02, and a 2026-10-04 rewrite made before
the neuro-lightbox repository was found) are in git history.
