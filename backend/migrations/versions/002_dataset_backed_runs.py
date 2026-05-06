from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SAMPLE_CHECKSUMS = [
    "517bc7516d7334c18e2cbf12eafea0adc2c0772a36c444bd59702a2de1e2fd0a",
    "7044a0760477263bfaa8d32a698a0863ff9395b73757e3e2c594af98a9d79416",
    "82097cc1a6cebfab108beb42859134a9c529ddf97a4c11a77bb240dd3bd15314",
    "e614bd6b3a0dc4ab53c6f546fe736e4a331685fb04e2b79be437a8f7fc1cff36",
    "c1b0f05cad83aad3b63596230dbc2f1a94febc55269dbd9ba031ae9286fa234c",
]


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_runs_dataset_id", "runs", ["dataset_id"])
    op.create_foreign_key(
        "fk_runs_dataset_id_datasets",
        "runs",
        "datasets",
        ["dataset_id"],
        ["id"],
    )

    datasets = sa.table(
        "datasets",
        sa.column("name", sa.String()),
        sa.column("symbols", postgresql.ARRAY(sa.String())),
        sa.column("timeframe", sa.String()),
        sa.column("start_date", sa.Date()),
        sa.column("end_date", sa.Date()),
        sa.column("row_count", sa.BigInteger()),
        sa.column("file_path", sa.Text()),
        sa.column("checksum", sa.String()),
    )
    start_date = date(2020, 1, 1)
    end_date = date(2024, 12, 31)
    row_count = 1305
    op.bulk_insert(
        datasets,
        [
            {
                "name": "AAPL Sample Daily",
                "symbols": ["AAPL"],
                "timeframe": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "file_path": "data/sample/AAPL_1d.parquet",
                "checksum": SAMPLE_CHECKSUMS[0],
            },
            {
                "name": "SPY Sample Daily",
                "symbols": ["SPY"],
                "timeframe": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "file_path": "data/sample/SPY_1d.parquet",
                "checksum": SAMPLE_CHECKSUMS[1],
            },
            {
                "name": "TSLA Sample Daily",
                "symbols": ["TSLA"],
                "timeframe": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "file_path": "data/sample/TSLA_1d.parquet",
                "checksum": SAMPLE_CHECKSUMS[2],
            },
            {
                "name": "MSFT Sample Daily",
                "symbols": ["MSFT"],
                "timeframe": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "file_path": "data/sample/MSFT_1d.parquet",
                "checksum": SAMPLE_CHECKSUMS[3],
            },
            {
                "name": "GOOG Sample Daily",
                "symbols": ["GOOG"],
                "timeframe": "1d",
                "start_date": start_date,
                "end_date": end_date,
                "row_count": row_count,
                "file_path": "data/sample/GOOG_1d.parquet",
                "checksum": SAMPLE_CHECKSUMS[4],
            },
        ],
    )


def downgrade() -> None:
    op.drop_constraint("fk_runs_dataset_id_datasets", "runs", type_="foreignkey")
    op.drop_index("ix_runs_dataset_id", table_name="runs")
    op.drop_column("runs", "dataset_id")
    quoted_checksums = ", ".join(f"'{checksum}'" for checksum in SAMPLE_CHECKSUMS)
    op.execute(f"DELETE FROM datasets WHERE checksum IN ({quoted_checksums})")
