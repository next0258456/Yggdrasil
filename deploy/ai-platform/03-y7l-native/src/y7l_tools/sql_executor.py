"""Track-B In-Process DuckDB RLS Executor, Superset Adapter, Saved Metrics & Direct Exporters."""

from __future__ import annotations

import csv
import json
import re
import time
import uuid
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb
import httpx
import redis
from openpyxl import Workbook

from y7l_tools.config import Settings
from y7l_tools.guard import audit_data_traps, validate_readonly_sql

_SAFE_REGION_RE = re.compile(r"^[A-Za-z0-9_\-\* ]+$")
_EMPTY_RESULT_MSG = "Bạn không có quyền truy cập hoặc dữ liệu không tồn tại"

SAVED_METRICS: dict[str, dict[str, str]] = {
    "net_revenue_by_region": {
        "title": "Doanh thu thuần theo khu vực",
        "sql": (
            "SELECT region, COUNT(*) AS order_count, "
            "SUM(quantity * unit_price) - SUM(discount) AS net_revenue "
            "FROM gold_sales_obt "
            "WHERE is_deleted = false "
            "GROUP BY region ORDER BY region"
        ),
    },
    "monthly_revenue": {
        "title": "Doanh thu thuần theo tháng",
        "sql": (
            "SELECT strftime(order_date, '%Y-%m') AS month, COUNT(*) AS order_count, "
            "SUM(quantity * unit_price) - SUM(discount) AS net_revenue "
            "FROM gold_sales_obt "
            "WHERE is_deleted = false "
            "GROUP BY 1 ORDER BY 1"
        ),
    },
    "top_customers": {
        "title": "Top khách hàng doanh thu cao nhất",
        "sql": (
            "SELECT c.customer_id, c.customer_name, c.region, "
            "SUM(s.quantity * s.unit_price) - SUM(s.discount) AS net_revenue "
            "FROM gold_sales_obt s "
            "JOIN dim_customers c ON s.customer_id = c.customer_id "
            "WHERE s.is_deleted = false AND c.customer_id NOT LIKE 'TEST_%' "
            "GROUP BY 1, 2, 3 ORDER BY net_revenue DESC LIMIT 10"
        ),
    },
    "order_count_summary": {
        "title": "Tổng hợp số lượng đơn hàng hợp lệ",
        "sql": (
            "SELECT region, COUNT(*) AS active_orders, SUM(quantity) AS total_units "
            "FROM gold_sales_obt "
            "WHERE is_deleted = false "
            "GROUP BY region ORDER BY region"
        ),
    },
    "fmcg_6m_monthly_summary": {
        "title": "Tổng hợp giao dịch FMCG 6.8M theo tháng",
        "sql": (
            "SELECT strftime(sales_date, '%Y-%m') AS month, COUNT(*) AS tx_count, "
            "SUM(quantity) AS total_units, ROUND(AVG(discount), 4) AS avg_discount "
            "FROM fmcg_sales_6m "
            "WHERE sales_date IS NOT NULL "
            "GROUP BY 1 ORDER BY 1"
        ),
    },
    "fmcg_6m_salesperson_ranking": {
        "title": "Top 10 nhân viên bán hàng FMCG 6.8M theo sản lượng",
        "sql": (
            "SELECT salesperson_id, region, COUNT(*) AS tx_count, "
            "SUM(quantity) AS total_units, ROUND(AVG(discount), 4) AS avg_discount "
            "FROM fmcg_sales_6m "
            "WHERE sales_date IS NOT NULL "
            "GROUP BY 1, 2 ORDER BY total_units DESC LIMIT 10"
        ),
    },
}


class MetricNotFoundError(KeyError):
    """Raised when a requested Saved Metric does not exist."""


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _render_markdown_table(columns: list[str], rows: list[list[Any]], max_rows: int = 20) -> str:
    if not columns:
        return ""
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, separator]
    for row in rows[:max_rows]:
        cells = [str(cell if cell is not None else "") for cell in row]
        lines.append("| " + " | ".join(cells) + " |")
    if len(rows) > max_rows:
        lines.append(f"\n*Hiển thị {max_rows}/{len(rows)} dòng đầu; toàn bộ nằm trong file đính kèm.*")
    return "\n".join(lines)


def _export_artifact(
    columns: list[str],
    rows: list[list[Any]],
    export_format: str,
    exports_dir: Path,
) -> Path:
    fmt = export_format.lower().strip()
    if fmt not in {"csv", "xlsx", "md"}:
        raise ValueError(f"Unsupported export format: {export_format}. Use csv, xlsx, or md.")

    exports_dir.mkdir(parents=True, exist_ok=True)
    filename = f"y7l_report_{uuid.uuid4().hex[:12]}.{fmt}"
    out_path = exports_dir / filename

    if fmt == "csv":
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            writer.writerows(rows)
    elif fmt == "xlsx":
        wb = Workbook()
        ws = wb.active
        ws.title = "Y7L_Report"
        ws.append(columns)
        for row in rows:
            ws.append(row)
        wb.save(out_path)
    else:
        md_content = _render_markdown_table(columns, rows, max_rows=len(rows) or 1)
        out_path.write_text(md_content, encoding="utf-8")

    return out_path


class SQLExecutor:
    """Executes read-only SQL with JWT Row-Level Security on DuckDB or Superset SQL Lab."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._metric_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._redis: redis.Redis | None = None
        if settings.redis_url.strip():
            try:
                client = redis.Redis.from_url(
                    settings.redis_url.strip(),
                    decode_responses=True,
                    socket_connect_timeout=1.0,
                    socket_timeout=1.0,
                )
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    def _run_duckdb_with_rls(self, sql: str, claims: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
        region = str(claims.get("region") or "").strip()
        role = str(claims.get("role") or "").strip()
        if not region or not _SAFE_REGION_RE.fullmatch(region):
            raise ValueError("Invalid region claim in JWT.")

        sales_parquet = self.settings.data_path / "gold_sales_obt.parquet"
        customers_parquet = self.settings.data_path / "dim_customers.parquet"
        if not sales_parquet.exists() or not customers_parquet.exists():
            raise FileNotFoundError(
                f"Parquet datasets not found in {self.settings.data_path}. Run data/seed_data.py first."
            )

        sales_path_sql = sales_parquet.as_posix().replace("'", "''")
        cust_path_sql = customers_parquet.as_posix().replace("'", "''")

        fmcg_parquet = self.settings.fmcg_sales_file
        con = duckdb.connect(":memory:")
        try:
            if region != "*" and role != "admin":
                con.execute(
                    f"CREATE VIEW gold_sales_obt AS SELECT * FROM read_parquet('{sales_path_sql}') WHERE region = '{region}'"
                )
                con.execute(
                    f"CREATE VIEW dim_customers AS SELECT * FROM read_parquet('{cust_path_sql}') WHERE region = '{region}'"
                )
                if fmcg_parquet is not None:
                    fmcg_path_sql = fmcg_parquet.as_posix().replace("'", "''")
                    con.execute(
                        "CREATE VIEW fmcg_sales_6m AS "
                        "SELECT *, CASE WHEN salesperson_id <= 12 THEN 'North' ELSE 'South' END AS region "
                        f"FROM read_parquet('{fmcg_path_sql}') "
                        f"WHERE (CASE WHEN salesperson_id <= 12 THEN 'North' ELSE 'South' END) = '{region}'"
                    )
            else:
                con.execute(
                    f"CREATE VIEW gold_sales_obt AS SELECT * FROM read_parquet('{sales_path_sql}')"
                )
                con.execute(
                    f"CREATE VIEW dim_customers AS SELECT * FROM read_parquet('{cust_path_sql}')"
                )
                if fmcg_parquet is not None:
                    fmcg_path_sql = fmcg_parquet.as_posix().replace("'", "''")
                    con.execute(
                        "CREATE VIEW fmcg_sales_6m AS "
                        "SELECT *, CASE WHEN salesperson_id <= 12 THEN 'North' ELSE 'South' END AS region "
                        f"FROM read_parquet('{fmcg_path_sql}')"
                    )

            cursor = con.execute(sql)
            columns = [desc[0] for desc in (cursor.description or [])]
            raw_rows = cursor.fetchall()
            rows = [[_serialize_cell(col) for col in row] for row in raw_rows]
            return columns, rows
        finally:
            con.close()

    def _run_superset_sqllab(self, sql: str, raw_jwt: str) -> tuple[list[str], list[list[Any]]]:
        endpoint = f"{self.settings.superset_url.rstrip('/')}/api/v1/sqllab/execute/"
        payload = {"sql": sql, "runAsync": False}
        headers = {"Authorization": f"Bearer {raw_jwt}", "Content-Type": "application/json"}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()

        col_defs = body.get("columns", [])
        columns = [col["name"] if isinstance(col, dict) else str(col) for col in col_defs]
        data = body.get("data", [])
        if not columns and data and isinstance(data[0], dict):
            columns = list(data[0].keys())
        rows = [[_serialize_cell(item.get(col)) for col in columns] for item in data]
        return columns, rows

    def execute_sql_rls(
        self,
        sql: str,
        claims: dict[str, Any],
        raw_jwt: str = "",
        export_format: str = "csv",
    ) -> dict[str, Any]:
        """Validate read-only SQL, enforce JWT RLS, execute, and export artifact directly."""
        clean_sql = validate_readonly_sql(sql)
        warnings = audit_data_traps(clean_sql)

        t0 = time.perf_counter()
        if self.settings.superset_url.strip():
            columns, rows = self._run_superset_sqllab(clean_sql, raw_jwt)
            engine = "superset_sqllab"
        else:
            columns, rows = self._run_duckdb_with_rls(clean_sql, claims)
            engine = "duckdb_in_memory"
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        if not rows:
            return {
                "empty": True,
                "message": _EMPTY_RESULT_MSG,
                "row_count": 0,
                "columns": columns,
                "artifact_filename": None,
                "artifact_url": None,
                "markdown_preview": "",
                "data_trap_warnings": warnings,
                "execution_ms": elapsed_ms,
                "engine": engine,
                "rls_region": claims.get("region"),
            }

        artifact_path = _export_artifact(columns, rows, export_format, self.settings.exports_dir)
        preview = _render_markdown_table(columns, rows, max_rows=20)
        return {
            "empty": False,
            "message": f"Truy vấn thành công ({len(rows)} dòng).",
            "row_count": len(rows),
            "columns": columns,
            "artifact_filename": artifact_path.name,
            "artifact_url": f"/artifacts/{artifact_path.name}",
            "markdown_preview": preview,
            "data_trap_warnings": warnings,
            "execution_ms": elapsed_ms,
            "engine": engine,
            "rls_region": claims.get("region"),
        }

    def list_saved_metrics(self) -> list[dict[str, str]]:
        """List Flow-1 Saved Metrics definitions."""
        return [
            {"name": name, "title": spec["title"]}
            for name, spec in SAVED_METRICS.items()
        ]

    def execute_saved_metric(
        self,
        metric_name: str,
        claims: dict[str, Any],
        export_format: str = "csv",
    ) -> dict[str, Any]:
        """Execute deterministic Flow-1 Saved Metric with 60s cache and JWT RLS."""
        if metric_name not in SAVED_METRICS:
            raise MetricNotFoundError(f"Unknown saved metric: {metric_name}")

        region = str(claims.get("region") or "*")
        role = str(claims.get("role") or "sales")
        cache_key = f"y7l:metric:{metric_name}:{region}:{role}:{export_format}"

        if self._redis is not None:
            try:
                cached_json = self._redis.get(cache_key)
                if cached_json:
                    payload = json.loads(cached_json)
                    payload["cached"] = True
                    return payload
            except Exception:
                pass

        mem_hit = self._metric_cache.get(cache_key)
        if mem_hit is not None and time.time() < mem_hit[0]:
            payload = dict(mem_hit[1])
            payload["cached"] = True
            return payload

        spec = SAVED_METRICS[metric_name]
        result = self.execute_sql_rls(
            sql=spec["sql"],
            claims=claims,
            export_format=export_format,
        )
        result["metric_name"] = metric_name
        result["title"] = spec["title"]
        result["cached"] = False

        if self._redis is not None:
            try:
                self._redis.setex(cache_key, 60, json.dumps(result, ensure_ascii=False))
            except Exception:
                pass
        self._metric_cache[cache_key] = (time.time() + 60.0, dict(result))
        return result
