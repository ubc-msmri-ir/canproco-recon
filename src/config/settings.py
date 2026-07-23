from dataclasses import dataclass, field
from pathlib import Path


# SOP-class values in `files.filetype` that carry an MR acquisition date.
MR_FILETYPES: tuple[str, ...] = (
    "MR Image Storage",
    "Enhanced MR Image Storage",
)


@dataclass
class ReconSettings:
    mysql_url: str
    output_dir: Path
    log_dir: Path
    mnt_prefix: str = "/mnt"
    mr_filetypes: tuple[str, ...] = field(default_factory=lambda: MR_FILETYPES)
    # Max number of other `files` rows to try when the primary file has no date.
    max_fallback_files: int = 50
