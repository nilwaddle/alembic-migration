"""Add_table_Fff

Revision ID: 3b937294d244
Revises: ed09fc88935e
Create Date: 2024-06-25 15:27:09.172006

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b937294d244'
down_revision: Union[str, None] = 'ed09fc88935e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('fff',
    sa.Column('ddd', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('ddd')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('fff')
    # ### end Alembic commands ###
