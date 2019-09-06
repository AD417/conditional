"""remove_freshmen_project

Revision ID: 4ac8ff82410a
Revises: d1a06ab54211
Create Date: 2019-09-06 11:21:28.515040

"""

# revision identifiers, used by Alembic.
revision = '4ac8ff82410a'
down_revision = 'd1a06ab54211'

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('freshman_eval_data', 'freshman_project',
               existing_type=postgresql.ENUM('Pending', 'Passed', 'Failed', name='freshman_project_enum'),
               nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('freshman_eval_data', 'freshman_project',
               existing_type=postgresql.ENUM('Pending', 'Passed', 'Failed', name='freshman_project_enum'),
               nullable=False)
    # ### end Alembic commands ###
