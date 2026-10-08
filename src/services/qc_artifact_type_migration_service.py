import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from adapters.excel.qc_artifact_type import QCArtifactTypeExcelAdapter
from adapters.mysql.db import SequenceRepository
from config.settings import QCReconSettings

logger = logging.getLogger(__name__)

# Written for SQL NULL in the backup CSV, so NULL and "" restore distinctly.
NULL_MARKER = r"\N"
STATE_COLUMNS = ["id", "QC_artifacts", "QC_artifact_types"]
# QC_artifacts value meaning "Yes" (see domain.QC_row.ARTIFACT).
HAS_ARTIFACTS = 1

# (QC_artifacts, QC_artifact_types)
State = tuple[int | None, str | None]


@dataclass
class MigrationSummary:
    rows_read: int = 0
    rows_skipped: int = 0
    sequences_targeted: int = 0
    sequences_changed: int = 0
    sequences_updated: int = 0
    verified_ok: int = 0
    verified_failed: int = 0
    dry_run: bool = False
    files: dict[str, Path] = field(default_factory=dict)


class QCArtifactTypeMigrationService:
    def __init__(self, sequence_repository: SequenceRepository, settings: QCReconSettings, timestamp: str):
        self._sequence_repository = sequence_repository
        self._settings = settings
        self._timestamp = timestamp

    def migrate(self, input_csv: Path, dry_run: bool = False) -> MigrationSummary:
        """Apply the QC artifact types from ``input_csv`` in a single transaction."""
        summary = MigrationSummary(dry_run=dry_run)

        # 1. Load + validate. Any invalid row aborts before the database is touched.
        logger.info("Step 1/5: loading %s", input_csv)
        adapter = QCArtifactTypeExcelAdapter(input_csv)
        summary.rows_read = len(adapter.rows) + len(adapter.errors)
        if adapter.errors:
            raise ValueError(f"{len(adapter.errors)} invalid row(s) in {input_csv}; nothing was changed")
        lookup_df = adapter.to_dataframe()

        # 2. Build the update groups, one per lookup row.
        logger.info("Step 2/5: building update plan")
        groups: list[tuple[str, list[int], State]] = []
        expected: dict[int, State] = {}
        for row in lookup_df.itertuples(index=False):
            label = f"{row.qc_comments!r} ({row.category})"
            if row.qc_artifact_type is None:
                logger.warning("Skipping %s: no QC_artifact_type", label)
                summary.rows_skipped += 1
                continue
            state: State = (HAS_ARTIFACTS, row.qc_artifact_type)
            ids = sorted(set(row.sequence_ids))
            for sequence_id in ids:
                previous = expected.setdefault(sequence_id, state)
                if previous != state:
                    raise ValueError(
                        f"Sequence {sequence_id} is assigned both {previous[1]} and {state[1]}; nothing was changed"
                    )
            groups.append((label, ids, state))
        summary.sequences_targeted = len(expected)
        logger.info("%d update groups covering %d sequences", len(groups), len(expected))

        # 3. Back up the current values of every targeted sequence.
        logger.info("Step 3/5: backing up current values")
        current = self._save_state(sorted(expected), "backup", summary)
        self._require_all_exist(expected, current)
        summary.sequences_changed = sum(
            not self._same_state(current[i], expected_state) for i, expected_state in expected.items()
        )
        logger.info(
            "%d of %d sequences will change (the rest already hold the target value)",
            summary.sequences_changed, summary.sequences_targeted,
        )

        if dry_run:
            for label, ids, state in groups:
                logger.info("[dry-run] %s: %d sequences -> QC_artifacts=%s, QC_artifact_types=%s",
                            label, len(ids), *state)
            logger.info("Dry run: no changes written")
            return summary

        # 4. Apply all groups in one transaction.
        logger.info("Step 4/5: applying updates in a single transaction")
        summary.sequences_updated = self._apply(groups)

        # 5. Verify.
        logger.info("Step 5/5: verifying")
        self._verify(expected, "verification", summary)
        return summary

    def rollback(self, backup_csv: Path, dry_run: bool = False) -> MigrationSummary:
        """Restore QC_artifacts / QC_artifact_types from a backup CSV in a single transaction."""
        summary = MigrationSummary(dry_run=dry_run)

        logger.info("Step 1/4: loading backup %s", backup_csv)
        expected = self._read_state(backup_csv)
        summary.rows_read = summary.sequences_targeted = len(expected)

        # Snapshot the current state, so the rollback itself can be undone.
        logger.info("Step 2/4: backing up current values before rollback")
        current = self._save_state(sorted(expected), "pre_rollback_backup", summary)
        self._require_all_exist(expected, current)
        summary.sequences_changed = sum(
            not self._same_state(current[i], expected_state) for i, expected_state in expected.items()
        )
        logger.info("%d of %d sequences will be restored", summary.sequences_changed, summary.sequences_targeted)

        ids_by_state: dict[State, list[int]] = {}
        for sequence_id, state in sorted(expected.items()):
            ids_by_state.setdefault(state, []).append(sequence_id)
        groups = [(f"restore {state}", ids, state) for state, ids in ids_by_state.items()]

        if dry_run:
            logger.info("Dry run: no changes written")
            return summary

        logger.info("Step 3/4: restoring in a single transaction")
        summary.sequences_updated = self._apply(groups)

        logger.info("Step 4/4: verifying")
        self._verify(expected, "rollback_verification", summary)
        return summary

    def _apply(self, groups: list[tuple[str, list[int], State]]) -> int:
        session = self._sequence_repository.session()
        updated = 0
        try:
            for label, ids, (qc_artifacts, qc_artifact_types) in groups:
                matched = self._sequence_repository.update_qc_artifacts(
                    session, ids, qc_artifacts, qc_artifact_types
                )
                logger.info("%s: %d sequences -> QC_artifacts=%s, QC_artifact_types=%s",
                            label, matched, qc_artifacts, qc_artifact_types)
                updated += matched
            session.commit()
            logger.info("Committed %d row updates", updated)
        except Exception:
            session.rollback()
            logger.exception("Update failed; transaction rolled back, database unchanged")
            raise
        finally:
            session.close()
        return updated

    def _verify(self, expected: dict[int, State], name: str, summary: MigrationSummary) -> None:
        actual = self._sequence_repository.get_qc_artifact_states(sorted(expected))
        records = []
        for sequence_id, (exp_artifacts, exp_types) in sorted(expected.items()):
            state = actual.get(sequence_id)
            act = (state["QC_artifacts"], state["QC_artifact_types"]) if state else (None, None)
            records.append({
                "id": sequence_id,
                "expected_QC_artifacts": exp_artifacts,
                "actual_QC_artifacts": act[0],
                "expected_QC_artifact_types": exp_types,
                "actual_QC_artifact_types": act[1],
                "ok": state is not None and self._same_state(state, (exp_artifacts, exp_types)),
            })
        df = pd.DataFrame(records, dtype=object)
        path = self._settings.output_dir / f"qc_artifact_types_{name}_{self._timestamp}.csv"
        df.to_csv(path, index=False, na_rep=NULL_MARKER)
        summary.files[name] = path

        summary.verified_ok = int(df["ok"].sum())
        summary.verified_failed = len(df) - summary.verified_ok
        if summary.verified_failed:
            logger.error("Verification FAILED for %d of %d sequences; see %s",
                         summary.verified_failed, len(df), path)
        else:
            logger.info("Verification passed for all %d sequences; see %s", len(df), path)

    def _save_state(self, sequence_ids: list[int], name: str, summary: MigrationSummary) -> dict[int, dict]:
        states = self._sequence_repository.get_qc_artifact_states(sequence_ids)
        df = pd.DataFrame(
            [{"id": i, **states[i]} for i in sequence_ids if i in states],
            columns=STATE_COLUMNS,
            dtype=object,
        )
        path = self._settings.output_dir / f"qc_artifact_types_{name}_{self._timestamp}.csv"
        df.to_csv(path, index=False, na_rep=NULL_MARKER)
        summary.files[name] = path
        logger.info("Saved current values of %d sequences to %s", len(df), path)
        return states

    @staticmethod
    def _read_state(path: Path) -> dict[int, State]:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        missing = set(STATE_COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"Backup {path} is missing columns: {sorted(missing)}")
        states: dict[int, State] = {}
        for row in df.itertuples(index=False):
            qc_artifacts = None if row.QC_artifacts == NULL_MARKER else int(row.QC_artifacts)
            qc_artifact_types = None if row.QC_artifact_types == NULL_MARKER else row.QC_artifact_types
            states[int(row.id)] = (qc_artifacts, qc_artifact_types)
        return states

    @staticmethod
    def _require_all_exist(expected: dict[int, State], current: dict[int, dict]) -> None:
        missing = sorted(set(expected) - set(current))
        if missing:
            raise ValueError(f"{len(missing)} sequence id(s) not found in the database; nothing was changed: {missing}")

    @staticmethod
    def _same_state(state: dict, expected: State) -> bool:
        exp_artifacts, exp_types = expected
        if state["QC_artifacts"] != exp_artifacts:
            return False
        act_types = state["QC_artifact_types"]
        if act_types == exp_types:
            return True
        if act_types is None or exp_types is None:
            return False
        # Compare as JSON so '["2", "4"]' matches '["2","4"]'.
        try:
            return json.loads(act_types) == json.loads(exp_types)
        except json.JSONDecodeError:
            return False
