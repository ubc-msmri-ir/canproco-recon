import logging
from pandas import DataFrame

from adapters.mysql.db import QCRepository
from config.settings import QCReconSettings
from domain.QC_row import QCRow

logger = logging.getLogger(__name__)

class CanProCoResearchQCService:
    def __init__(
            self,
            settings: QCReconSettings,
            qc_repo: QCRepository
    ):
        self._settings = settings
        self._qc_repo = qc_repo

    def run(self) -> DataFrame:
        logger.info("Running CanProCo Research QC Service")
        raw = self._qc_repo.get_canproco_research_qc()
        rows = [QCRow.model_validate(r).model_dump() for r in raw]
        logger.info("Fetched %d rows of CanProCo Research QC data", len(rows))
        
        columns = [
            "subject_name",
            "timepoint",
            "sequence_id",
            "sequence_name",
            "body_part_examined",
            "predicted_sequence_type",
            "sequence_status",
            "sequence_qc_artifact",
            "sequence_qc_artifact_types",
            "sequence_qc_comments",
            "upload_file_path",
        ]
        return DataFrame(rows, columns=columns)