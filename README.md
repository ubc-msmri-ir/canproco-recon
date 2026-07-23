# CanProCo Recon — Acquisition Date Reconciliation

Reconciles the `scans.acquisition_date` values in the CanProCo MySQL database against
the **DICOM source of truth**. During CanProCo reconciliation (merging the GRP and SQL
databases), some acquisition dates in SQL were found not to match GRP. The DICOM header
is authoritative, so this tool reads `AcquisitionDate` directly from the relevant DICOM
file for each upload and produces a reviewable report plus a manually-runnable SQL
transaction to correct the discrepancies.

## What this project does

For each `data_upload_id` in an input CSV:

1. **Find the DICOM record** — one row in `files` where `data_upload_id` matches and
   `filetype IN ('MR Image Storage', 'Enhanced MR Image Storage')`. When several rows
   qualify, the lowest `files.id` is chosen (one acquisition date applies to the whole
   series).
2. **Parse subject + timepoint** from `files.location`, e.g.
   `/ISILON/msmri-repo/data/canproco/toronto/CAN_01_FOU_008/m60c/ax-t2-3mm__11_1808/raw`
   → subject `CAN_01_FOU_008`, timepoint `M60C` (uppercased).
3. **Resolve the absolute path** = `location` + `filename`. If it doesn't exist, retry
   once with a `/mnt` prefix (`/ISILON/...` → `/mnt/ISILON/...`).
4. **Read `AcquisitionDate` (0008,0022)** from the DICOM header.
5. **Resolve the scan** in `scans` by joining on `(subjects.name, scans.timepoint)`,
   pulling `scans.id` and the current `acquisition_date` (bulk lookup for all pairs in
   one query).
6. **Emit outputs** — a per-row result CSV, a skip/error log, and a SQL transaction that
   updates only the discrepancies.

Every per-upload failure (no file row, unparseable location, missing path, missing
`AcquisitionDate`, no scan match, ambiguous multi-scan match) is **logged and skipped**;
the batch always completes and prints a summary.

## Project layout

- `src/cli/reconcile_acquisition_dates.py` — runnable entrypoint
- `src/config/` — `settings.py` (`ReconSettings`) and `env.py` (`EnvConfigAdapter`)
- `src/domain/mysql/models.py` — `File`, `Subject`, `Scan` ORM models
- `src/adapters/dicom.py` — path resolution + `AcquisitionDate` reader
- `src/adapters/mysql/db.py` — `FileRepository`, `ScanRepository`
- `src/services/reconciliation_service.py` — orchestration + output writers
- `data/` — input CSVs (the `UploadID` list)
- `output/` — result CSV + generated `.sql`
- `log/` — skip/error CSV

The SQL adapter, config, and domain patterns follow the sibling
`canproco-clinical-qc-migration` project.

## Requirements

- Python 3.10+
- MySQL read access to the CanProCo clinical repo (`files`, `subjects`, `scans`)
- File-system access to the DICOM directories referenced by `files.location`
  (directly or under `/mnt`)

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Environment variables are loaded from a `.env` at the project root (see `.env.example`):

```
MYSQL_HOST=...
MYSQL_PORT=3306
MYSQL_USER=...
MYSQL_PASSWORD=...
MYSQL_DB=clinicalrepo

# Optional: prefix tried when an absolute DICOM path is not found as-is (default /mnt)
MNT_PREFIX=/mnt
```

> **Note:** `.env` contains live database credentials and is gitignored. Do not commit it.

## Input

A CSV containing a single `UploadID` column (a header is required). Extra columns are
ignored; duplicate and non-numeric ids are dropped. Place it under `data/`.

```
UploadID
12345
12346
12347
```

## Usage

```bash
python src/cli/reconcile_acquisition_dates.py --input data/your_ids.csv
```

The entrypoint adds `src/` to `sys.path`, so no `PYTHONPATH` setup is needed.

## Outputs

Files are named after the input stem plus a run timestamp.

- **`output/<stem>_reconciliation_<ts>.csv`** — one row per successfully resolved upload:
  `data_upload_id, subject_name, timepoint, dcm_path, acquisition_date,
  current_acquisition_date, scans_id, changed`. The `changed` flag marks rows where the
  DICOM date differs from the current DB value.
- **`log/<stem>_skipped_<ts>.csv`** — `data_upload_id, reason` for every skipped upload.
- **`output/<stem>_update_acquisition_dates_<ts>.sql`** — a manually-runnable transaction:

  ```sql
  START TRANSACTION;
  UPDATE scans SET acquisition_date = '2019-05-01' WHERE id = 123;  -- was '2019-04-30' (upload 456, CAN_01_FOU_008 M60C)
  COMMIT;

  -- ROLLBACK: run this block to restore the previous values after commit.
  -- START TRANSACTION;
  -- UPDATE scans SET acquisition_date = '2019-04-30' WHERE id = 123;  -- restore (...)
  -- COMMIT;
  ```

  Only discrepancies (`changed = True`) generate `UPDATE` statements. The commented
  rollback block carries reverse `UPDATE`s that restore each prior value, so the change
  is reversible even after `COMMIT`.

## Data safety

This tool is **read-only** against the database — it never writes to MySQL itself. The
generated `.sql` is for you to review and run manually against the correct environment.
Inspect the result CSV and the `UPDATE`/rollback statements before executing.

## Troubleshooting

- **`ModuleNotFoundError: config`** — run the CLI via the provided entrypoint (it puts
  `src/` on the path); if importing modules directly, add `src/` to `PYTHONPATH`.
- **Database connection errors** — verify `MYSQL_*` in `.env` and network access to the host.
- **Everything skipped with "path not found"** — the DICOM directories aren't mounted at
  the expected location; check `files.location` and set `MNT_PREFIX` accordingly.
- **"multiple scans matched"** — more than one scan shares that `(subject, timepoint)`;
  these are skipped as ambiguous and listed in the skip log for manual resolution.
