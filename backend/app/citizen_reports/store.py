from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.schemas.citizen_report import CitizenReport, CitizenReportStatus


class CitizenReportStore:
    def __init__(self, root: Path):
        self.root = root
        self.uploads_dir = root / "uploads"
        self.db_path = root / "reports.sqlite3"
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS citizen_reports (
                    id TEXT PRIMARY KEY,
                    aoi_id TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_reports_created_at ON citizen_reports(created_at)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_citizen_reports_status ON citizen_reports(status)"
            )

    def save(self, report: CitizenReport, image_data: bytes, extension: str) -> CitizenReport:
        image_path = self.uploads_dir / f"{report.id}{extension}"
        image_path.write_bytes(image_data)
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO citizen_reports
                (id, aoi_id, category, status, created_at, updated_at, image_path, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.id,
                    report.aoi_id,
                    report.category,
                    report.status,
                    report.created_at.isoformat(),
                    report.updated_at.isoformat(),
                    str(image_path),
                    report.model_dump_json(),
                ),
            )
        return report

    def list(self, *, aoi_id: str | None = None, status: CitizenReportStatus | None = None) -> list[CitizenReport]:
        clauses: list[str] = []
        params: list[str] = []
        if aoi_id:
            clauses.append("aoi_id = ?")
            params.append(aoi_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload_json FROM citizen_reports{where} ORDER BY created_at DESC", params
            ).fetchall()
        return [CitizenReport.model_validate_json(row["payload_json"]) for row in rows]

    def get(self, report_id: str) -> CitizenReport | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM citizen_reports WHERE id = ?", (report_id,)
            ).fetchone()
        return CitizenReport.model_validate_json(row["payload_json"]) if row else None

    def image_path(self, report_id: str) -> Path | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT image_path FROM citizen_reports WHERE id = ?", (report_id,)
            ).fetchone()
        if not row:
            return None
        path = Path(row["image_path"]).resolve()
        uploads = self.uploads_dir.resolve()
        if uploads not in path.parents or not path.is_file():
            return None
        return path

    def update_status(
        self,
        report_id: str,
        *,
        status: CitizenReportStatus,
        officer_id: str,
        notes: str,
        updated_at: datetime,
    ) -> CitizenReport | None:
        report = self.get(report_id)
        if report is None:
            return None
        updated = report.model_copy(
            update={
                "status": status,
                "officer_id": officer_id,
                "officer_notes": notes,
                "updated_at": updated_at,
            }
        )
        with self._connect() as connection:
            connection.execute(
                """UPDATE citizen_reports
                SET status = ?, updated_at = ?, payload_json = ? WHERE id = ?""",
                (status, updated_at.isoformat(), updated.model_dump_json(), report_id),
            )
        return updated

