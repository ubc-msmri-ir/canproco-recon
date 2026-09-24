from datetime import date
from typing import Optional

from sqlalchemy import select, tuple_

from domain.mysql.models import File, Scan, Subject, Sequence


class FileRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_one_file_per_upload(
        self,
        data_upload_ids: list[int],
        filetypes: tuple[str, ...],
    ) -> dict[int, dict]:
        """Return one qualifying file per ``data_upload_id``.

        When several rows qualify, the lowest ``files.id`` wins (deterministic;
        a single acquisition date applies to the whole series).
        Result maps ``data_upload_id`` -> ``{file_id, filename, location}``.
        """
        if not data_upload_ids:
            return {}

        statement = (
            select(
                File.id.label("file_id"),
                File.data_upload_id,
                File.filename,
                File.location,
            )
            .where(
                File.data_upload_id.in_(data_upload_ids),
                File.filetype.in_(filetypes),
            )
            .order_by(File.data_upload_id, File.id)
        )

        with self._session_factory() as session:
            rows = session.execute(statement).mappings().all()

        chosen: dict[int, dict] = {}
        for row in rows:
            uid = row["data_upload_id"]
            if uid not in chosen:  # rows are ordered by id ascending -> first is lowest
                chosen[uid] = {
                    "file_id": row["file_id"],
                    "filename": row["filename"],
                    "location": row["location"],
                }
        return chosen

    def get_additional_files(
        self,
        data_upload_id: int,
        filetypes: tuple[str, ...],
        exclude_file_id: int,
        limit: int = 50,
    ) -> list[dict]:
        """Fallback candidates: other qualifying `files` rows for one upload.

        Ordered by ascending ``files.id``, excluding the already-tried
        ``exclude_file_id``, capped at ``limit``. Fetched lazily, only when the
        primary file yields no acquisition date.
        """
        statement = (
            select(
                File.id.label("file_id"),
                File.filename,
                File.location,
            )
            .where(
                File.data_upload_id == data_upload_id,
                File.filetype.in_(filetypes),
                File.id != exclude_file_id,
            )
            .order_by(File.id)
            .limit(limit)
        )

        with self._session_factory() as session:
            rows = session.execute(statement).mappings().all()

        return [
            {"file_id": r["file_id"], "filename": r["filename"], "location": r["location"]}
            for r in rows
        ]


class ScanRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get_scans_by_pairs(
        self,
        pairs: list[tuple[str, str]],
    ) -> dict[tuple[str, str], list[dict]]:
        """Bulk-resolve scans for ``(subject_name, timepoint)`` pairs.

        Returns a mapping ``(name, timepoint)`` -> list of
        ``{scan_id, acquisition_date}``. A key with more than one entry signals
        an ambiguous match that the caller should skip.
        """
        if not pairs:
            return {}

        unique_pairs = list({(name, tp) for name, tp in pairs})

        statement = select(
            Scan.id.label("scan_id"),
            Scan.acquisition_date,
            Subject.name.label("subject_name"),
            Scan.timepoint,
        ).join(
            Subject, Scan.subject_id == Subject.id
        ).where(
            tuple_(Subject.name, Scan.timepoint).in_(unique_pairs)
        )

        with self._session_factory() as session:
            rows = session.execute(statement).mappings().all()

        result: dict[tuple[str, str], list[dict]] = {}
        for row in rows:
            key = (row["subject_name"], row["timepoint"])
            result.setdefault(key, []).append(
                {
                    "scan_id": row["scan_id"],
                    "acquisition_date": row["acquisition_date"],
                }
            )
        return result

class QCRepository:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self.canproco_research_site_ids = [25, 26, 27, 28, 29] # CanProCo Research Site Id
        self.canproco_clinical_site_ids = [1, 2, 3, 4, 5] # CanProCo Clinical Site Id
        

    def get_canproco_research_qc(
            self
    ) -> list[dict]:
        """
        Fetch all rows from the Sequences table join with the Scans table and join with the Subjects table.
        Returns a list of dictionaries containing sequence, scan, and subject information.
        """
        statement = select(
            Sequence.id.label("sequence_id"),
            Sequence.series_description.label("sequence_name"),
            Scan.timepoint.label("timepoint"),
            Subject.name.label("subject_name"),
            Sequence.status.label("sequence_status"),
            Sequence.QC_artifacts.label("sequence_qc_artifact"),
            Sequence.QC_comments.label("sequence_qc_comments")
        ).join(
            Scan, Sequence.scan_id == Scan.id
        ).join(
            Subject, Scan.subject_id == Subject.id
        ).where(
            Sequence.site_id.in_(self.canproco_research_site_ids)
        )

        with self._session_factory() as session:
            rows: list[dict] = session.execute(statement).mappings().all()

        return rows
