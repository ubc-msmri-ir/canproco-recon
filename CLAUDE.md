# What is this directory?
This project directory is a git repo. It contains the source code for fixing any discrepancy between the GRP and SQL databases found during CanProCo reconciliation.

# Problem
CanProCo reconciliation is the process of merging the GRP and SQL databases to search for discrepancies. One finding was that the acquisition dates in the SQL database don't match those stated in GRP. The DICOM files are the source of truth.

# Solution

Develop a Python script that reconciles `scans.acquisition_date` against the DICOM
source-of-truth for each `data_upload_id` listed in an input CSV.

## Config / conventions
- Reuse the patterns from `canproco-clinical-qc-migration`: `EnvConfigAdapter` + `.env`
  (`MYSQL_*` composed into a `mysql+pymysql://` URL), the `sessionmaker` /
  `session_factory` repository pattern, and the ORM style in
  `domain/mysql/models.py`. Reuse the `Scan` model; add `File` and `Subject` models.
- CLI entrypoint lives under `src/cli`.

## Input
- CSV with a `UploadID` column (list of `data_upload_id`), read from `data/`.

## Per `data_upload_id`
1. Fetch **one** row from `files` where `data_upload_id` matches and
   `filetype IN ('MR Image Storage', 'Enhanced MR Image Storage')`. When several
   rows qualify, pick the lowest `files.id` deterministically (one acquisition date
   applies to the whole series). No row → log + skip.
2. From `location`, parse `subject_name` via the `CAN_\d\d_...` pattern and
   `timepoint` as the next path segment, normalized to **uppercase**. Example:
   `/ISILON/msmri-repo/data/canproco/toronto/CAN_01_FOU_008/m60c/ax-t2-3mm__11_1808/raw`
   → subject `CAN_01_FOU_008`, timepoint `M60C`.
3. Absolute path = `location` + `filename`. If it doesn't exist, retry with a `/mnt`
   prefix; still missing → log + skip.
4. `pydicom.dcmread(path, stop_before_pixels=True, specific_tags=['AcquisitionDate'])`
   and read **AcquisitionDate (0008,0022)** only. If it is missing/empty, **fall
   back** to the other qualifying `files` rows for the same `data_upload_id` (fetched
   lazily, ordered by `files.id`, capped at `max_fallback_files`); the first row whose
   DICOM carries a non-empty AcquisitionDate wins. Each fallback attempt is logged. If
   no candidate yields a date → log + skip.
5. Bulk-resolve `scans.id` and the current `acquisition_date` with a single join on
   the `(subjects.name, scans.timepoint)` pairs:
   `SELECT scans.id, scans.acquisition_date, subjects.name, scans.timepoint
    FROM scans JOIN subjects ON scans.subject_id = subjects.id
    WHERE (subjects.name, scans.timepoint) IN ((...), ...)`.
   0 or >1 matches for a pair → log + skip.

## Outputs
- **Result CSV** (`output/`): columns `data_upload_id`, `subject_name`, `timepoint`,
  `dcm_path`, `acquisition_date`, `current_acquisition_date`, `scans_id`, `changed`.
- **Skip/error log** (`log/`): `data_upload_id` + reason, with an end-of-run summary count.
- **Transaction `.sql`** (`output/`): `START TRANSACTION;` followed by
  `UPDATE scans SET acquisition_date = '...' WHERE id = ...;` **only where the DICOM
  date differs** from the current value, then `COMMIT;`. Append a commented rollback
  block of reverse `UPDATE`s restoring each prior `acquisition_date` so the change is
  reversible after commit. Intended to be run manually.

## Behavior
- Log-and-continue on every per-id failure; the batch always completes and prints a
  summary (processed / updated / skipped).

# Note
For communicating with the SQL database, refer to the scripts in the `canproco-clinical-qc-migration` project, under the `adapters`, `config`, and `domain` subdirectories. If you need additional information, such as the schema of specific SQL tables, please let me know.

# Project Structure
- `src/adapters`
- `log`
- `output`
- `src/cli`
- `src/domain`
- `src/config`
- `src/services`
- `.gitignore`
- `data`
- `.venv`
- `.env`
- `requirements.txt`

# SQL tables

mysql> DESCRIBE files;
+---------------------------+-----------------+------+-----+-------------------+-------------------+
| Field                     | Type            | Null | Key | Default           | Extra             |
+---------------------------+-----------------+------+-----+-------------------+-------------------+
| id                        | bigint unsigned | NO   | PRI | NULL              | auto_increment    |
| filename                  | varchar(150)    | NO   |     | NULL              |                   |
| name_in_archive           | varchar(4096)   | NO   |     | NULL              |                   |
| file_size                 | varchar(100)    | NO   |     | NULL              |                   |
| location                  | varchar(4096)   | NO   |     | NULL              |                   |
| md5sum                    | varchar(100)    | NO   |     | NULL              |                   |
| orig_md5sum               | varchar(100)    | NO   |     | NULL              |                   |
| sequence_id               | bigint unsigned | YES  | MUL | NULL              |                   |
| filetype                  | varchar(100)    | NO   |     | NULL              |                   |
| parse_comment             | varchar(500)    | YES  |     | NULL              |                   |
| header_file_id            | bigint unsigned | YES  | MUL | NULL              |                   |
| data_upload_id            | bigint unsigned | YES  | MUL | NULL              |                   |
| create_time               | datetime        | NO   |     | CURRENT_TIMESTAMP | DEFAULT_GENERATED |
| conversionSoftware_id     | bigint unsigned | YES  | MUL | NULL              |                   |
| creation_processing_phase | tinyint         | YES  |     | NULL              |                   |
| pixel_size                | varchar(50)     | YES  |     | NULL              |                   |
| conversion_software_id    | int             | YES  |     | NULL              |                   |
| scanner_info_id           | int             | YES  |     | NULL              |                   |
+---------------------------+-----------------+------+-----+-------------------+-------------------+

mysql> DESCRIBE subjects;
+------------------------+-----------------+------+-----+---------+----------------+
| Field                  | Type            | Null | Key | Default | Extra          |
+------------------------+-----------------+------+-----+---------+----------------+
| id                     | bigint unsigned | NO   | PRI | NULL    | auto_increment |
| name                   | varchar(100)    | NO   |     | NULL    |                |
| birth_date             | date            | YES  |     | NULL    |                |
| sex                    | varchar(20)     | YES  |     | NULL    |                |
| disease_onset_date     | date            | YES  |     | NULL    |                |
| disease_diagnosis_date | date            | YES  |     | NULL    |                |
| site_id                | bigint unsigned | NO   | MUL | NULL    |                |
+------------------------+-----------------+------+-----+---------+----------------+

