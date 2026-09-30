"""create article_contents

Revision ID: 0002
Revises: 0001
"""

from pathlib import Path

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _execute_sql_file(direction: str) -> None:
    [sql_file] = _MIGRATIONS_DIR.glob(f"{revision}_*.{direction}.sql")
    connection = op.get_bind().execution_options(no_parameters=True)
    connection.exec_driver_sql(sql_file.read_text())


def upgrade() -> None:
    _execute_sql_file("up")


def downgrade() -> None:
    _execute_sql_file("down")
