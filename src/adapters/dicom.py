import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pydicom

logger = logging.getLogger(__name__)


def resolve_path(location: str, filename: str, mnt_prefix: str = "/mnt") -> Optional[Path]:
    """Concat ``location`` and ``filename`` into an absolute path.

    If the direct path does not exist, retry once with ``mnt_prefix`` prepended
    (e.g. ``/ISILON/...`` -> ``/mnt/ISILON/...``). Returns ``None`` if neither
    candidate exists.
    """
    direct = Path(location) / filename
    if direct.exists():
        return direct

    # Prepend the mount prefix to the absolute path, preserving its leading slash.
    prefixed = Path(mnt_prefix) / str(direct).lstrip("/")
    if prefixed.exists():
        return prefixed

    return None


def read_acquisition_date(path: Path) -> Optional[date]:
    """Read AcquisitionDate (0008,0022) from a DICOM header.

    Returns a ``date`` or ``None`` when the tag is missing/empty/unparseable.
    """
    try:
        ds = pydicom.dcmread(
            str(path),
            stop_before_pixels=True,
            specific_tags=["AcquisitionDate"],
            force=True,
        )
    except Exception as exc:  # noqa: BLE001 - surface as a skip, not a crash
        logger.warning("Failed to read DICOM header at %s: %s", path, exc)
        return None

    raw = ds.get("AcquisitionDate", None)
    if not raw:
        return None

    try:
        return datetime.strptime(str(raw).strip(), "%Y%m%d").date()
    except ValueError:
        logger.warning("Unparseable AcquisitionDate '%s' at %s", raw, path)
        return None
