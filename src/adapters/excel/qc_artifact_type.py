import logging
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from domain.qc_artifact_type_lookup import CanProCoQCArtifactTypeLookup

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"QC_comments", "Clinical/Research", "sequence_ids", "count", "QC_artifact_type"}


class QCArtifactTypeExcelAdapter:
    """Reads the QC artifact type lookup CSV into validated rows.

    Invalid rows are collected in ``errors`` as ``(csv_line, message)`` rather
    than raised, so every problem in the file is reported in one pass.
    """

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        self.rows: list[CanProCoQCArtifactTypeLookup] = []
        self.errors: list[tuple[int, str]] = []

        # dtype=str + keep_default_na=False: "8" stays a string and blanks stay "".
        df = pd.read_csv(self.file_path, dtype=str, keep_default_na=False)
        df.columns = [col.strip() for col in df.columns]
        logger.info("Loaded %d rows from %s", len(df), self.file_path)

        missing_columns = REQUIRED_COLUMNS - set(df.columns)
        if missing_columns:
            raise ValueError(f"Missing required columns in {self.file_path}: {sorted(missing_columns)}")

        for index, record in enumerate(df.to_dict(orient="records")):
            csv_line = index + 2  # header is line 1
            try:
                self.rows.append(CanProCoQCArtifactTypeLookup.model_validate(record))
            except ValidationError as e:
                message = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
                self.errors.append((csv_line, message))
                logger.error("Invalid row at line %d: %s", csv_line, message)

        logger.info("%d valid rows, %d invalid rows", len(self.rows), len(self.errors))

    def to_dataframe(self) -> pd.DataFrame:
        """Valid rows as a DataFrame with columns
        qc_comments, category, sequence_ids, count, qc_artifact_type."""
        return pd.DataFrame(
            [row.model_dump() for row in self.rows],
            columns=list(CanProCoQCArtifactTypeLookup.model_fields),
        )
