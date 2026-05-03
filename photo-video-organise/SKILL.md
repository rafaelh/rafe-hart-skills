---
name: photo-video-organise
description: Organize large photo and video collections by moving and renaming files into a structured archive based on EXIF, filename, or filesystem date. Trigger when the user wants to organize, sort, tidy, or restructure a photo or video library; consolidate camera dumps; build a year/month archive; deduplicate photo folders; or rename files using their capture date. Handles CR2/CR3 RAW, JPG/JPEG, PNG, MP4, MOV, M4V, AVI, TIF, HEIC, and XMP sidecars; preserves RAW+JPEG and Live Photo (HEIC+MOV) pairs; never deletes files (quarantines duplicates and conflicts for the user to review); supports per-job undo. Cross-platform (Windows, macOS, Linux). Skip for tasks that aren't filesystem organization — photo editing, format conversion, cloud upload, recognition, and EXIF writing are out of scope.
---

# Photo & Video Organise

A safe, chunked, resumable organizer for large photo/video collections. Files move into a date-based archive structure; duplicates and conflicts go into user-review folders; nothing is ever deleted.

## Always do, in this order

1. **Bootstrap check.** `uv run scripts/bootstrap.py --check`. If non-zero, run `uv run scripts/bootstrap.py` and walk the user through any missing dependencies in plain language. Exiftool is the most common gap; install instructions are platform-specific (the script prints them).

2. **Detect interrupted jobs.** `uv run scripts/jobs.py list` and check for any `in_progress: true` entries. If found, surface to the user: *"Found an interrupted job from `<job_id>`: X groups completed, Y in progress. (a) resume, (b) start fresh, (c) leave alone for now."* Do not silently auto-resume.

3. **Inventory.** `uv run scripts/inventory.py <source-root> > /tmp/inventory.jsonl`. Read the stderr summary aloud to the user — counts of first-class / best-effort / excluded files. Flag any OneDrive cloud-only files surfaced.

4. **Strategy phase (relentless questioning).** Co-design `strategy.json` with the user via plain-language Q&A. Cover:
   - Source and destination roots (can be same → reorganize in place).
   - Date strategy: which sources, in what order. Default: `["exif:Composite:DateTimeOriginal", "filename:patterns", "mtime"]`.
   - Filename patterns to recognize (the script ships with 8 defaults; add for unfamiliar names spotted in the inventory).
   - Suspicious date thresholds (1980/2000-01-01 sentinels, min_year, reject_future).
   - Path template (default `{year}/{year}-{month:02d}/`) and per-format overrides (RAW/Video).
   - Rename: opt-in or off (default off — preserves camera filenames).
   - Dedup: yes or no. If the user is using fdupes or similar separately, set `dedup.enabled: false`.
   - OneDrive cloud-only handling: skip (default) or force-download.

   Save `strategy.json` to disk. Show the user a prose summary (`strategy.md`) and confirm before continuing.

5. **Sample preview.** `uv run scripts/plan.py --strategy strategy.json --inventory /tmp/inventory.jsonl --destination <dest> --sample 20`. Show the user 20 concrete proposed moves. If the user wants changes, return to step 4. Only proceed past this step with explicit user approval.

6. **Execute chunk by chunk.** For each chunk's plan: `uv run scripts/plan.py ... > plan.jsonl` then `uv run scripts/execute.py --plan plan.jsonl --source-root <src> --destination-root <dest> --job-id <id>`. After each chunk, summarize to the user (counts, failures, anomalies). If anomaly thresholds trip (>20% fallback rate, >5% lock or collision rate), pause and ask before continuing.

7. **End-of-job.** Surface to the user:
   - Job id and state-dir path (for undo).
   - Summary of `To_Delete/duplicates/`, `_conflicts/`, and `_needs-review/` folders, with what to do with each.
   - Anything that needs follow-up (locked files, suspicious dates, demotions).

## Never do

- Never call `mv`, `rm`, `cp`, `os.rename`, `os.remove`, or `shutil.move` directly on user files — always go through `execute.py` and `undo.py`.
- Never delete files. The skill quarantines; the user purges manually.
- Never proceed past the sample step without explicit user approval.
- Never paste raw error tracebacks at the user. Translate into plain language.
- Never write into the photo tree except into `To_Delete/`, `_conflicts/`, `_needs-review/`, or actual organized destinations.
- Never silently auto-resume an interrupted job.

## Plain-language communication

The target user is non-technical. When in doubt, translate.

- Bad: "Pillow can't decode CR3 due to HEIF wrapper limitations."
- Good: "Some Canon RAW files (CR3) need a more powerful tool — let me check it's installed."
- Bad: "PermissionError on 4 files."
- Good: "4 files were locked (likely Windows Defender or a photo viewer was using them). They're tracked — we can retry them at the end."
- Bad: "Strategy.json schema_version=1 validated."
- Good: "Got it. Here's what I'll do: [prose summary]. Sound right?"

## Out of scope (refuse politely, suggest alternatives)

- **Photo editing / rotation / color correction** — different tool category.
- **Format conversion** (HEIC→JPEG, CR2→DNG, MOV→MP4) — use a real photo/video tool. Suggest ImageMagick or ffmpeg.
- **Thumbnail generation** — different problem.
- **Cloud upload** (Google Photos, iCloud) — out of scope.
- **Face / object recognition / auto-tagging** — different tool category.
- **EXIF editing / writing back to files** — read only.
- **GPS-based organization** — date-based only for v1; GPS is read but not used for placement.
- **Watch / daemon mode** — one-shot job model.

If the user asks for any of the above, acknowledge, explain it's out of scope, and suggest the right tool category if you can.

## Format scope

- **First-class** (full EXIF support): JPG, JPEG, PNG, CR2, CR3, NEF, ARW, MP4, MOV, M4V, AVI, TIF, TIFF, HEIC, HEIF, XMP.
- **Best-effort** (uses filename / mtime fallback only — no EXIF): anything else not in the excluded list.
- **Excluded** (skipped, recorded as such): archives (.zip, .tar, .gz, .tgz, .rar, .7z), Photoshop (.psd, .psb), photo catalogs (.lrcat, .lrdata, .db, .sqlite).

## File layout

```
photo-video-organise/
├── SKILL.md                    # This file
├── scripts/
│   ├── bootstrap.py            # Setup check + per-platform install instructions
│   ├── inventory.py            # Walk source tree → inventory.jsonl
│   ├── read_exif.py            # Batch EXIF reader (JSONL output, one line per path)
│   ├── plan.py                 # strategy + inventory → plan.jsonl
│   ├── execute.py              # plan.jsonl → atomic moves with verification
│   ├── undo.py                 # Reverse a job by id
│   ├── jobs.py                 # list / show / purge jobs
│   └── lib/                    # Shared modules (do not invoke directly)
├── fixtures/                   # Test fixtures
└── bin/                        # Optional: drop bundled exiftool.exe here on Windows
```

## Strategy JSON shape (reference)

```json
{
  "schema_version": 1,
  "source_root": "/path/to/source",
  "destination_root": "/path/to/destination",
  "date_sources": [
    "exif:Composite:DateTimeOriginal",
    "exif:EXIF:DateTimeOriginal",
    "filename:patterns",
    "mtime"
  ],
  "filename_patterns": [
    "IMG_(\\d{4})(\\d{2})(\\d{2})_(\\d{2})(\\d{2})(\\d{2})",
    "VID_(\\d{4})(\\d{2})(\\d{2})_(\\d{2})(\\d{2})(\\d{2})",
    "(\\d{4})(\\d{2})(\\d{2})_(\\d{2})(\\d{2})(\\d{2})",
    "IMG-(\\d{4})(\\d{2})(\\d{2})-WA\\d+",
    "(\\d{4})-(\\d{2})-(\\d{2})",
    "(\\d{4})(\\d{2})(\\d{2})"
  ],
  "suspicious_dates": {
    "sentinels": ["1970-01-01", "1980-01-01", "2000-01-01"],
    "min_year": 1995,
    "reject_future": true
  },
  "path_template": "{year}/{year}-{month:02d}/",
  "format_rules": {
    "raw":   {"extensions": [".cr2", ".cr3", ".nef", ".arw"], "path_template": "{year}/{year}-{month:02d}/RAW/"},
    "video": {"extensions": [".mp4", ".mov", ".m4v", ".avi"], "path_template": "{year}/{year}-{month:02d}/Video/"}
  },
  "rename_template": null,
  "review_paths": {
    "needs_review": "_needs-review/{reason}/",
    "conflicts": "_conflicts/",
    "duplicates": "To_Delete/duplicates/"
  }
}
```

## Gotchas

Things the agent will get wrong if it forgets them:

- **Job state lives outside the photo tree**, in `platformdirs.user_state_dir("photo-organise")` (`~/Library/Application Support/photo-organise/jobs/<id>/` on macOS, `%LOCALAPPDATA%\photo-organise\jobs\<id>\` on Windows, `~/.local/state/photo-organise/jobs/<id>/` on Linux). Don't look for `.photo-organise/` in the destination folder; it's deliberately not there.
- **Cross-volume moves take roughly 2× the time** of same-volume (copy + SHA256 verify + delete). Tell the user this when source and destination are on different drives — a 100GB camera-dump-to-archive job can be an hour, not 30 minutes. The executor handles cross-volume detection automatically; you don't pick which mode to use.
- **OneDrive cloud-only files default to skip.** Reading a placeholder triggers a download. For a multi-GB OneDrive photo library, blindly processing would trigger a massive unintended sync. Inventory reports cloud-only counts; user must explicitly opt in.
- **Pair grouping is folder-scoped, not tree-wide.** `2019/IMG_1234.CR2` and `2020/IMG_1234.JPG` are unrelated. `IMG_1234.CR2` and `IMG_1234.JPG` in the same folder pair into one group with shared destination.
- **The skill never deletes.** Even with `dedup.enabled: true`, duplicates move to `To_Delete/duplicates/`. The user purges manually. If the user mentions running fdupes or another dedup tool separately, set `dedup.enabled: false` so this skill doesn't move duplicates that fdupes will handle.
- **Excluded extensions are skipped entirely**, not best-effort: `.zip`, `.tar`, `.psd`, `.lrcat`, `.db`, `.sqlite` and similar archive/catalog formats. If the user has a Lightroom catalog mixed in their photo dump, it won't move with the photos.
- **mtime is a lossy fallback.** A file copied to a new drive often has fresh mtime — meaning files might land in the wrong year/month bucket. The journal records `date_source` per group so demotions are auditable; tell the user when a chunk's fallback rate is high.
- **EXIF dates with no timezone are treated as naive local time.** Photos shot in different timezones during travel can land in folders that are off by hours (and sometimes a day) from "when it felt like" to the user. Acceptable for organization, surprising for the user — flag if relevant.
- **Source bytes are never deleted before verify completes.** This is the resume-safety invariant. If a cross-volume move is interrupted, the source still exists and resume retries cleanly. Same-volume moves are atomic renames — no partial state possible.
- **Suspicious EXIF dates get demoted, not used.** A camera with a dead battery often produces `1980-01-01 00:00:00` as DateTimeOriginal. The strategy demotes these to filename/mtime and tags the group with `date_demoted_from`. Don't trust any wholesale "1980" cluster.

## Behavior cheatsheet

| Situation | What happens |
|---|---|
| Source = destination | Reorganize in place; same-volume moves are atomic renames. |
| Cross-volume | Copy → SHA256 verify → delete source. Slower but bulletproof. |
| Destination already has identical file | Source group → `To_Delete/duplicates/` (preserves source folder structure). |
| Destination already has different file | Source group → `_conflicts/`. |
| No date determinable | Group → `_needs-review/no-date/`. |
| File locked (antivirus etc.) | 3 retries with exponential backoff, then logged as failure. |
| RAW+JPEG, HEIC+MOV, XMP sidecar | Move as one group with shared destination + shared rename. |
| Already-organized files | Skipped. Re-running is a no-op unless `--reorganize` flag is passed. |
| Interrupted (Ctrl+C, power loss) | Resume detected on next run; user prompted. Source bytes are never lost (verify-before-delete invariant). |
