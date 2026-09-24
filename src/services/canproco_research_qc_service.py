import logging
from pandas import DataFrame

from adapters.mysql.db import QCRepository
from config.settings import QCReconSettings

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
        research_qc_data = self._qc_repo.get_canproco_research_qc()
        logger.info("Fetched %d rows of CanProCo Research QC data", len(research_qc_data))
        return DataFrame(research_qc_data)