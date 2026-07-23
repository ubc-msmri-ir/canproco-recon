import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from adapters.dicom import read_acquisition_date, resolve_path
from adapters.mysql.db import FileRepository, ScanRepository
from config.settings import ReconSettings

logger = logging.getLogger(__name__)

# Subject folder like CAN_01_FOU_008; the segment immediately after it is the timepoint.
SUBJECT_RE = re.compile(r"^CAN_\d{2}_.+", re.IGNORECASE)

OUTPUT_COLUMNS = [
    "data_upload_id",
    "subject_name",
    "timepoint",
    "dcm_path",
    "acquisition_date",
    "current_acquisition_date",
    "scans_id",
    "changed",
]


@dataclass
class ReconResult:
    rows: list[dict] = field(default_factory=list)          # successfully resolved
    skips: list[dict] = field(default_factory=list)         # (data_upload_id, reason)
    fallback_count: int = 0                                  # dates sourced from a non-primary file
    result_csv_path: Optional[Path] = None
    sql_path: Optional[Path] = None
    log_path: Optional[Path] = None

    @property
    def changed_count(self) -> int:
        return sum(1 for r in self.rows if r["changed"])


def parse_location(location: str) -> tuple[Optional[str], Optional[str]]:
    """Extract (subject_name, uppercased timepoint) from a ``files.location`` path.

    Example: ``/ISILON/.../canproco/toronto/CAN_01_FOU_008/m60c/ax-t2/raw``
    -> ("CAN_01_FOU_008", "M60C"). Returns (None, None) if no subject segment found.
    """
    segments = [seg for seg in location.split("/") if seg]
    for idx, seg in enumerate(segments):
        if SUBJECT_RE.match(seg):
            if idx + 1 >= len(segments):
                return seg, None
            return seg, segments[idx + 1].upper()
    return None, None


class ReconciliationService:
    def __init__(
        self,
        settings: ReconSettings,
        file_repo: FileRepository,
        scan_repo: ScanRepository,
    ):
        self._settings = settings
        self._file_repo = file_repo
        self._scan_repo = scan_repo

    # ------------------------------------------------------------------ #
    def run(self, input_csv: Path, timestamp: Optional[str] = None) -> ReconResult:
        timestamp = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        result = ReconResult()

        upload_ids = self._read_upload_ids(input_csv)
        logger.info("Loaded %d unique data_upload_id(s) from %s", len(upload_ids), input_csv)

        files_map = self._file_repo.get_one_file_per_upload(
            upload_ids, self._settings.mr_filetypes
        )

        # Stage 1-4: resolve file -> path -> DICOM acquisition date, per upload.
        # If the primary file has no AcquisitionDate, fall back to other qualifying
        # `files` rows for the same upload (first non-empty date wins).
        resolved: list[dict] = []
        for uid in upload_ids:
            f = files_map.get(uid)
            if not f:
                self._skip(result, uid, "no MR file row found")
                continue

            subject, timepoint = parse_location(f["location"])
            if not subject or not timepoint:
                self._skip(result, uid, f"could not parse subject/timepoint from location: {f['location']}")
                continue

            acq, used_path, used_file_id, attempts = self._resolve_acquisition_date(uid, f)
            if acq is None:
                self._skip(result, uid, "no usable AcquisitionDate; tried " + "; ".join(attempts))
                continue

            if used_file_id != f["file_id"]:
                result.fallback_count += 1

            resolved.append(
                {
                    "data_upload_id": uid,
                    "subject_name": subject,
                    "timepoint": timepoint,
                    "dcm_path": str(used_path),
                    "acquisition_date": acq,
                }
            )

        # Stage 5: bulk-resolve scans for all resolved (subject, timepoint) pairs.
        pairs = [(r["subject_name"], r["timepoint"]) for r in resolved]
        scans_map = self._scan_repo.get_scans_by_pairs(pairs)

        for r in resolved:
            uid = r["data_upload_id"]
            key = (r["subject_name"], r["timepoint"])
            matches = scans_map.get(key, [])
            if len(matches) == 0:
                self._skip(result, uid, f"no scan matched subject={r['subject_name']} timepoint={r['timepoint']}")
                continue
            if len(matches) > 1:
                ids = ", ".join(str(m["scan_id"]) for m in matches)
                self._skip(result, uid, f"multiple scans matched subject={r['subject_name']} timepoint={r['timepoint']} (ids: {ids})")
                continue

            scan_id = matches[0]["scan_id"]
            current: date = matches[0]["acquisition_date"]
            dcm_date: date = r["acquisition_date"]

            result.rows.append(
                {
                    "data_upload_id": uid,
                    "subject_name": r["subject_name"],
                    "timepoint": r["timepoint"],
                    "dcm_path": r["dcm_path"],
                    "acquisition_date": dcm_date.isoformat(),
                    "current_acquisition_date": current.isoformat() if current else "",
                    "scans_id": scan_id,
                    "changed": dcm_date != current,
                }
            )

        self._write_outputs(result, input_csv, timestamp)
        self._log_summary(result, len(upload_ids))
        return result

    # ------------------------------------------------------------------ #
    def _resolve_acquisition_date(
        self, uid: int, primary: dict
    ) -> tuple[Optional[date], Optional[Path], Optional[int], list[str]]:
        """Return (acquisition_date, path, file_id, attempts) for an upload.

        Tries the primary file first; if it yields no date, lazily fetches the
        other qualifying `files` rows for this upload and tries them in id order.
        The first non-empty AcquisitionDate wins. ``attempts`` records every
        candidate that failed, for skip-log context.
        """
        attempts: list[str] = []

        # 1) Primary file (lowest files.id).
        acq, path = self._read_candidate(uid, primary, is_fallback=False, attempts=attempts)
        if acq is not None:
            return acq, path, primary["file_id"], attempts

        # 2) Fallback: other qualifying files rows for this upload.
        additional = self._file_repo.get_additional_files(
            uid,
            self._settings.mr_filetypes,
            exclude_file_id=primary["file_id"],
            limit=self._settings.max_fallback_files,
        )
        if not additional:
            logger.info(
                "FALLBACK upload=%s: primary file_id=%s had no AcquisitionDate and no other MR files exist",
                uid, primary["file_id"],
            )
            return None, None, None, attempts

        logger.info(
            "FALLBACK upload=%s: primary file_id=%s had no AcquisitionDate; trying %d other MR file(s)",
            uid, primary["file_id"], len(additional),
        )
        for cand in additional:
            acq, path = self._read_candidate(uid, cand, is_fallback=True, attempts=attempts)
            if acq is not None:
                logger.info(
                    "FALLBACK upload=%s: AcquisitionDate %s resolved from file_id=%s (%s)",
                    uid, acq.isoformat(), cand["file_id"], path,
                )
                return acq, path, cand["file_id"], attempts

        logger.info(
            "FALLBACK upload=%s: no AcquisitionDate found across %d candidate file(s)",
            uid, len(attempts),
        )
        return None, None, None, attempts

    def _read_candidate(
        self, uid: int, cand: dict, is_fallback: bool, attempts: list[str]
    ) -> tuple[Optional[date], Optional[Path]]:
        """Resolve one candidate file's path and read its AcquisitionDate."""
        abs_path = resolve_path(cand["location"], cand["filename"], self._settings.mnt_prefix)
        if abs_path is None:
            tried = Path(cand["location"]) / cand["filename"]
            attempts.append(f"file_id={cand['file_id']}: path not found ({tried})")
            if is_fallback:
                logger.info("FALLBACK upload=%s: file_id=%s path not found, trying next", uid, cand["file_id"])
            return None, None

        acq = read_acquisition_date(abs_path)
        if acq is None:
            attempts.append(f"file_id={cand['file_id']}: no AcquisitionDate ({abs_path})")
            if is_fallback:
                logger.info("FALLBACK upload=%s: file_id=%s (%s) has no AcquisitionDate, trying next", uid, cand["file_id"], abs_path)
            return None, None

        return acq, abs_path

    # ------------------------------------------------------------------ #
    def _read_upload_ids(self, input_csv: Path) -> list[int]:
        df = pd.read_csv(input_csv)
        if "UploadID" not in df.columns:
            raise ValueError(f"Input CSV {input_csv} must contain a 'UploadID' column; got {list(df.columns)}")
        ids = pd.to_numeric(df["UploadID"], errors="coerce").dropna().astype(int)
        # Preserve first-seen order, drop duplicates.
        seen: set[int] = set()
        ordered: list[int] = []
        for v in ids.tolist():
            if v not in seen:
                seen.add(v)
                ordered.append(v)
        return ordered

    def _skip(self, result: ReconResult, uid: int, reason: str) -> None:
        logger.warning("SKIP data_upload_id=%s: %s", uid, reason)
        result.skips.append({"data_upload_id": uid, "reason": reason})

    # ------------------------------------------------------------------ #
    def _write_outputs(self, result: ReconResult, input_csv: Path, timestamp: str) -> None:
        stem = input_csv.stem
        out_dir = self._settings.output_dir
        log_dir = self._settings.log_dir

        # Result CSV (all successfully resolved rows).
        result_df = pd.DataFrame(result.rows, columns=OUTPUT_COLUMNS)
        result.result_csv_path = out_dir / f"{stem}_reconciliation_{timestamp}.csv"
        result_df.to_csv(result.result_csv_path, index=False)

        # Skip/error log CSV.
        result.log_path = log_dir / f"{stem}_skipped_{timestamp}.csv"
        pd.DataFrame(result.skips, columns=["data_upload_id", "reason"]).to_csv(
            result.log_path, index=False
        )

        # Transaction SQL (only discrepancies).
        result.sql_path = out_dir / f"{stem}_update_acquisition_dates_{timestamp}.sql"
        result.sql_path.write_text(self._build_sql(result, timestamp))

    def _build_sql(self, result: ReconResult, timestamp: str) -> str:
        changed = [r for r in result.rows if r["changed"]]

        lines: list[str] = []
        lines.append(f"-- CanProCo acquisition-date reconciliation")
        lines.append(f"-- Generated: {timestamp}")
        lines.append(f"-- Discrepancies to update: {len(changed)}")
        lines.append("-- Review, then run manually.")
        lines.append("")

        if not changed:
            lines.append("-- No discrepancies found; nothing to update.")
            lines.append("")
            return "\n".join(lines)

        lines.append("START TRANSACTION;")
        lines.append("")
        for r in changed:
            lines.append(
                f"UPDATE scans SET acquisition_date = '{r['acquisition_date']}' "
                f"WHERE id = {r['scans_id']};  "
                f"-- was '{r['current_acquisition_date']}' "
                f"(upload {r['data_upload_id']}, {r['subject_name']} {r['timepoint']})"
            )
        lines.append("")
        lines.append("COMMIT;")
        lines.append("")
        lines.append("-- ===================================================================")
        lines.append("-- ROLLBACK: run this block to restore the previous values after commit.")
        lines.append("-- ===================================================================")
        lines.append("-- START TRANSACTION;")
        for r in changed:
            lines.append(
                f"-- UPDATE scans SET acquisition_date = '{r['current_acquisition_date']}' "
                f"WHERE id = {r['scans_id']};  "
                f"-- restore (upload {r['data_upload_id']}, {r['subject_name']} {r['timepoint']})"
            )
        lines.append("-- COMMIT;")
        lines.append("")
        return "\n".join(lines)

    def _log_summary(self, result: ReconResult, total: int) -> None:
        logger.info("### RECONCILIATION COMPLETE ###")
        logger.info("Uploads in input:        %d", total)
        logger.info("Resolved rows:           %d", len(result.rows))
        logger.info("  via fallback file:     %d", result.fallback_count)
        logger.info("Discrepancies (changed): %d", result.changed_count)
        logger.info("Skipped:                 %d", len(result.skips))
        logger.info("Result CSV: %s", result.result_csv_path)
        logger.info("Skip log:   %s", result.log_path)
        logger.info("SQL file:   %s", result.sql_path)
