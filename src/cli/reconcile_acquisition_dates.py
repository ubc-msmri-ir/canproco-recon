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

from adapters.mysql.db import FileRepository, ScanRepository
from config.env import EnvConfigAdapter
from services.reconciliation_service import ReconciliationService

logger = logging.getLogger(__name__)


def configure_logging(log_dir: Path, timestamp: str) -> Path:
    """Send logs to both the console and a per-run file in ``log_dir``."""
    log_file = log_dir / f"reconcile_{timestamp}.log"
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


def main(input_csv: Path) -> None:
    settings = EnvConfigAdapter().load().recon

    # One timestamp for the run: shared by the log file and the output filenames.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = configure_logging(settings.log_dir, timestamp)
    logger.info("Run log: %s", log_file)

    engine = create_engine(settings.mysql_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to connect to the database: {exc}")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    service = ReconciliationService(
        settings=settings,
        file_repo=FileRepository(session_factory),
        scan_repo=ScanRepository(session_factory),
    )
    service.run(input_csv, timestamp=timestamp)


def argument_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile scans.acquisition_date against DICOM AcquisitionDate."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input CSV containing a 'UploadID' column.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = argument_parser()
    if not args.input.exists():
        raise SystemExit(f"Input CSV not found: {args.input}")
    main(args.input)
