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

from adapters.mysql.db import SequenceRepository
from config.env import EnvConfigAdapter
from services.canproco_qc_comments_summary import CanProCoQCCommentsSummaryService

logger = logging.getLogger(__name__)

def configure_logging(log_dir: Path, timestamp: str) -> Path:
    """Send logs to both the console and a per-run file in ``log_dir``."""
    log_file = log_dir / f"fetch_canproco_qc_comments_summary_{timestamp}.log"
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

    service = CanProCoQCCommentsSummaryService(sequence_repository=SequenceRepository(session_factory), settings=settings)
    df = service.run()
    output_file = output or (settings.output_dir / f"canproco_qc_comments_summary_{timestamp}.csv")
    df.to_csv(output_file, index=False)
    logger.info("Output written to: %s", output_file)

def argument_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch CanProCo QC Comments Summary and optionally save it to a CSV file."
    )
    # Optional: specify the output CSV file for saving the fetched CanProCo Research QC data.
    parser.add_argument(
        "--output",
        type=Path,
        nargs="?",
        help="Optional Path to output CSV for saving the fetched CanProCo QC Summary.",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = argument_parser()
    main(output=args.output)