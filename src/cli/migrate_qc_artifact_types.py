import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

# Put src/ on the path so `config`, `domain`, `adapters`, `services` import cleanly
# whether run as `python src/cli/migrate_qc_artifact_types.py` or `-m`.
SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from adapters.mysql.db import SequenceRepository
from config.env import EnvConfigAdapter
from services.qc_artifact_type_migration_service import QCArtifactTypeMigrationService

logger = logging.getLogger(__name__)


def configure_logging(log_dir: Path, timestamp: str) -> Path:
    """Send logs to both the console and a per-run file in ``log_dir``."""
    log_file = log_dir / f"migrate_qc_artifact_types_{timestamp}.log"
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


def main(input_csv: Path | None, rollback: Path | None, dry_run: bool) -> int:
    settings = EnvConfigAdapter().load().qc_recon

    # One timestamp for the run: shared by the log file and the output filenames.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = configure_logging(settings.log_dir, timestamp)
    logger.info("Run log: %s", log_file)
    logger.info("Mode: %s%s", "rollback" if rollback else "migrate", " (dry run)" if dry_run else "")

    # Set up the database session and repositories
    engine = create_engine(settings.mysql_url)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to connect to the database: {exc}")

    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    service = QCArtifactTypeMigrationService(
        sequence_repository=SequenceRepository(session_factory),
        settings=settings,
        timestamp=timestamp,
    )

    try:
        if rollback:
            summary = service.rollback(rollback, dry_run=dry_run)
        else:
            summary = service.migrate(input_csv, dry_run=dry_run)
    except Exception:
        logger.exception("Run aborted")
        return 1

    logger.info(
        "Summary: rows_read=%d rows_skipped=%d sequences_targeted=%d sequences_changed=%d "
        "sequences_updated=%d verified_ok=%d verified_failed=%d dry_run=%s",
        summary.rows_read, summary.rows_skipped, summary.sequences_targeted, summary.sequences_changed,
        summary.sequences_updated, summary.verified_ok, summary.verified_failed, summary.dry_run,
    )
    for name, path in summary.files.items():
        logger.info("%s: %s", name, path)
    return 1 if summary.verified_failed else 0


def argument_parser() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bulk-update sequences.QC_artifact_types (and set QC_artifacts=1) from a QC comment lookup CSV, "
                    "or roll back a previous run from its backup CSV."
    )
    parser.add_argument(
        "input_csv",
        type=Path,
        nargs="?",
        help="Lookup CSV with QC_comments, Clinical/Research, sequence_ids, count, QC_artifact_type columns.",
    )
    parser.add_argument(
        "--rollback",
        type=Path,
        metavar="BACKUP_CSV",
        help="Restore QC_artifacts / QC_artifact_types from a backup CSV written by a previous run.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate, write the backup and log the planned changes without updating the database.",
    )
    args = parser.parse_args()
    if bool(args.input_csv) == bool(args.rollback):
        parser.error("give exactly one of input_csv or --rollback BACKUP_CSV")
    return args


if __name__ == "__main__":
    args = argument_parser()
    sys.exit(main(input_csv=args.input_csv, rollback=args.rollback, dry_run=args.dry_run))
