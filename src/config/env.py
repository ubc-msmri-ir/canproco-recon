import os
from pathlib import Path

from dotenv import load_dotenv

from config.settings import AppSettings, ReconSettings, QCReconSettings

# Project root is two levels up from this file: src/config/env.py -> src -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Prefer a project-root .env; fall back to a src/config/.env if present.
for _candidate in (PROJECT_ROOT / ".env", Path(__file__).resolve().parent / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)
        break


class EnvConfigAdapter:
    """Loads MySQL connection + output locations from the environment."""

    def load(self) -> AppSettings:
        required = ("MYSQL_HOST", "MYSQL_PORT", "MYSQL_USER", "MYSQL_PASSWORD", "MYSQL_DB")
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

        host = os.getenv("MYSQL_HOST")
        port = os.getenv("MYSQL_PORT")
        user = os.getenv("MYSQL_USER")
        password = os.getenv("MYSQL_PASSWORD")
        database = os.getenv("MYSQL_DB")

        mysql_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

        output_dir = PROJECT_ROOT / "output"
        log_dir = PROJECT_ROOT / "log"
        output_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        recon_settings = ReconSettings(
            mysql_url=mysql_url,
            output_dir=output_dir,
            log_dir=log_dir,
            mnt_prefix=os.getenv("MNT_PREFIX", "/mnt"),
        )
        qc_recon_settings = QCReconSettings(
            mysql_url=mysql_url,
            output_dir=output_dir,
            log_dir=log_dir,
        )
        return AppSettings(
            recon=recon_settings,
            qc_recon=qc_recon_settings,
        )
