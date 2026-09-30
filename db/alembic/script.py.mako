"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
"""

from pathlib import Path

from alembic import op

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = None
depends_on = None

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _execute_sql_file(direction: str) -> None:
    [sql_file] = _MIGRATIONS_DIR.glob(f"{revision}_*.{direction}.sql")
    # no_parameters sends the file through the simple query protocol,
    # which is what allows several statements in one execute.
    connection = op.get_bind().execution_options(no_parameters=True)
    connection.exec_driver_sql(sql_file.read_text())


def upgrade() -> None:
    _execute_sql_file("up")


def downgrade() -> None:
    _execute_sql_file("down")
