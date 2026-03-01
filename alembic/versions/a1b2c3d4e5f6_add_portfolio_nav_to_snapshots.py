"""add portfolio_nav total_units net_inflow to portfolio_snapshots

Revision ID: a1b2c3d4e5f6
Revises: 9c78e7c30ff5
Create Date: 2026-03-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9c78e7c30ff5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'portfolio_snapshots',
        sa.Column('portfolio_nav', sa.Numeric(precision=12, scale=6), nullable=True,
                  comment='组合净值（起始1.000000）')
    )
    op.add_column(
        'portfolio_snapshots',
        sa.Column('total_units', sa.Numeric(precision=20, scale=4), nullable=True,
                  comment='组合份额（用于发行/赎回）')
    )
    op.add_column(
        'portfolio_snapshots',
        sa.Column('net_inflow', sa.Numeric(precision=16, scale=4), nullable=True,
                  comment='当日净资金流入（正=买入,负=卖出）')
    )


def downgrade() -> None:
    op.drop_column('portfolio_snapshots', 'net_inflow')
    op.drop_column('portfolio_snapshots', 'total_units')
    op.drop_column('portfolio_snapshots', 'portfolio_nav')
