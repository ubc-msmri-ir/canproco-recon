import logging
import pandas as pd
from sqlalchemy import false
from adapters.mysql.db import SequenceRepository
from config.settings import QCReconSettings

logger = logging.getLogger(__name__)

class CanProCoQCCommentsSummaryService:
    def __init__(self, sequence_repository: SequenceRepository, settings: QCReconSettings):
        self._sequence_repository = sequence_repository
        self._settings = settings
        self.clinical_site_ids: list[int] = [1, 2, 3, 4, 5]
        self.research_site_ids: list[int] = [25, 26, 27, 28, 29]
        self.include_null_comments: bool = False

    def run(self) -> pd.DataFrame:
        logger.info("Running CanProCo QC Comments Summary Service")
        logger.info(
            "Fetching CanProCo QC Comments Summary for clinical_site_ids=%s, research_site_ids=%s, include_null_comments=%s",
            self.clinical_site_ids,
            self.research_site_ids,
            self.include_null_comments,
        )
        try:
            df = self._sequence_repository.get_canproco_qc_comment_summary_by_site_category(
                clinical_site_ids=self.clinical_site_ids,
                research_site_ids=self.research_site_ids,
                include_null_comments=self.include_null_comments,
            )
        except ValueError as e:
            logger.error("Error fetching CanProCo QC Comments Summary: %s", e)
            return pd.DataFrame(columns=["QC_comments", "Clinical/Research", "sequence_ids", "count"])
        logger.info("Fetched CanProCo QC Comments Summary with %d rows", len(df))
        return df