from alembic import command
from alembic.config import Config
import os
import sys

# Simply generate a fresh script
os.system('docker exec spot-optimizer-backend alembic revision -m "targeted_schema_fixes"')
