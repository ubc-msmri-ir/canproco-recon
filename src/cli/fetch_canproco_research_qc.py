import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Put src/ on the path so `config`, `domain`, `adapters`, `services` import cleanly
# whether run as `python src/cli/reconcile_acquisition_dates.py` or `-m`.
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from adapters.mysql.db import QCRepository
from config.env import EnvConfigAdapter
from services.canproco_research_qc_service import CanProCoResearchQCService

logger = logging.getLogger(__name__)

def configure_logging(log_dir: Path, timestamp: str) -> Path:
    """Send logs to both the console and a per-run file in ``log_dir``."""
    log_file = log_dir / f"fetch_canproco_research_qc_{timestamp}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
        force=True,
    )
    return log_file

def main(output: Path):
    settings = EnvConfigAdapter().load().qc_recon
    if output is not None:
        settings.output_dir = output.parent

    # One timestamp for the run: shared by the log file and the output filenames.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = configure_logging(settings.log_dir, timestamp)
    logger.info("Run log: %s", log_file)

    # Set up the database session and repositories
    engine = create_engine(settings.mysql_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to connect to the database: {exc}")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # Run the CanProCo Research QC Service
    qc_repo = QCRepository(session_factory)
    service = CanProCoResearchQCService(settings, qc_repo)
    research_qc_df = service.run()
    logger.info("Fetched CanProCo Research QC data with %d rows", len(research_qc_df))

    # Log the number of subjects for each timepoint fetched
    if not research_qc_df.empty:
        subjects_per_timepoint = research_qc_df.groupby("timepoint")["subject_name"].nunique()
        for timepoint, subject_count in subjects_per_timepoint.items():
            logger.info("Timepoint '%s' has %d unique subjects", timepoint, subject_count)

    # Optionally, save the fetched data to a CSV file
    output_file = settings.output_dir / f"canproco_research_qc_{timestamp}.csv"
    research_qc_df.to_csv(output_file, index=False)
    logger.info("Saved CanProCo Research QC data to %s", output_file)

def argument_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CanProCo Research QC data and optionally save it to a CSV file."
    )
    # Optional: specify the output CSV file for saving the fetched CanProCo Research QC data.
    parser.add_argument(
        "--output",
        type=Path,
        nargs="?",
        help="Optional Path to output CSV for saving the fetched CanProCo Research QC data.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = argument_parser()
    main(args.output)