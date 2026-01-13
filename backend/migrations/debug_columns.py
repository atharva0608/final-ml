
from sqlalchemy import create_engine, inspect
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

def list_columns():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    columns = inspector.get_columns('users')
    col_names = [c['name'] for c in columns]
    print("User Columns:", col_names)

if __name__ == "__main__":
    list_columns()
