from sqlalchemy import create_engine, inspect
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/spot_optimizer")

def list_tables():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    print("Tables:", inspector.get_table_names())

if __name__ == "__main__":
    list_tables()
