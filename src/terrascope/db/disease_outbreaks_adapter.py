import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from terrascope.db.engine import Session
from terrascope.db.geojson import EMPTY_FEATURE_COLLECTION
from terrascope.db.models import DiseaseOutbreakReport
from terrascope.lib.disease_outbreaks import current_as_geojson

logger = logging.getLogger(__name__)

# The report's fields as the collector builds them (lib/disease_outbreaks.py::build_report)
# and the columns they are stored in.
_COLUMNS = {
    "title": "title", "disease": "disease", "key": "disease_key", "kind": "kind",
    "countries": "countries", "ended": "ended", "ends_unplaced": "ends_unplaced",
    "published": "published", "modified": "modified", "summary": "summary",
    "url_name": "url_name",
}


def _row_to_report(row: DiseaseOutbreakReport) -> dict:
    report = {field: getattr(row, column) for field, column in _COLUMNS.items()}
    report["don_id"] = row.don_id
    return report


class DiseaseOutbreaksAdapter:
    """Real adapter for WHO Disease Outbreak News reports, backed by SQLAlchemy."""

    def upsert_report(self, report: dict) -> None:
        """UPSERTs a report keyed on its WHO identifier."""
        values = {column: report[field] for field, column in _COLUMNS.items()}
        stmt = pg_insert(DiseaseOutbreakReport).values(don_id=report["don_id"], **values)
        stmt = stmt.on_conflict_do_update(
            index_elements=[DiseaseOutbreakReport.don_id],
            set_={column: stmt.excluded[column] for column in values},
        )
        try:
            with Session() as session:
                session.execute(stmt)
                session.commit()
        except Exception as e:
            logger.error(f"Error saving disease outbreak report {report['don_id']}: {e}")

    def get_current_as_geojson(self, active_days: float = 45) -> str:
        """The current outbreaks as GeoJSON points, plus the `unplaced` list."""
        try:
            with Session() as session:
                reports = [_row_to_report(r) for r in session.scalars(select(DiseaseOutbreakReport))]
            return current_as_geojson(reports, active_days)
        except Exception as e:
            logger.error(f"Error building disease outbreaks GeoJSON: {e}")
            return EMPTY_FEATURE_COLLECTION

    def prune_expired(self, expiry_days: float) -> int:
        """Deletes reports published more than `expiry_days` ago. Returns how many."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=expiry_days)
        with Session() as session:
            result = session.execute(
                delete(DiseaseOutbreakReport).where(DiseaseOutbreakReport.published < cutoff)
            )
            session.commit()
            return result.rowcount


class FakeDiseaseOutbreaksAdapter:
    """In-memory fake for WHO Disease Outbreak News reports, matching
    DiseaseOutbreaksAdapter's method contracts."""

    def __init__(self):
        self._reports: dict[str, dict] = {}

    def upsert_report(self, report: dict) -> None:
        self._reports[report["don_id"]] = dict(report)

    def get_current_as_geojson(self, active_days: float = 45) -> str:
        return current_as_geojson(list(self._reports.values()), active_days)

    def prune_expired(self, expiry_days: float) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=expiry_days)
        expired = [k for k, r in self._reports.items() if r["published"] < cutoff]
        for k in expired:
            del self._reports[k]
        return len(expired)
