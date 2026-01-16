import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))

from backend.models.base import Base, engine
from backend.models.platform_settings import PlatformSettings

def migrate():
    print("Creating platform_settings table...")
    PlatformSettings.__table__.create(bind=engine, checkfirst=True)
    print("Migration complete!")

if __name__ == "__main__":
    migrate()
