import json
import logging

import pandas as pd

from domain.QC_row import ARTIFACT_DESCRIPTION

logger = logging.getLogger(__name__)

# Code used for "*remove QC", "others" and any other non-numeric entry.
OTHER_ARTIFACT_CODE = "8"


def normalize_qc_artifact_type(value) -> str | None:
    """Turn a spreadsheet entry into the `sequences.QC_artifact_types` format.

    e.g. "8" -> '["8"]', " 2, 4 " -> '["2","4"]', "*remove QC" -> '["8"]'.
    Returns None for an empty entry; raises ValueError for an unknown numeric code.
    """
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    text = str(value).strip()
    if not text:
        return None

    codes: list[str] = []
    for token in (t.strip() for t in text.split(",")):
        if not token:
            continue
        if token.isdigit():
            code = str(int(token))
            if code not in ARTIFACT_DESCRIPTION:
                raise ValueError(f"Unknown QC artifact type code: {token!r}")
        else:
            logger.warning("Non-numeric QC artifact type %r mapped to %s", token, OTHER_ARTIFACT_CODE)
            code = OTHER_ARTIFACT_CODE
        if code not in codes:
            codes.append(code)

    if not codes:
        return None
    return json.dumps(codes, separators=(",", ":"))
