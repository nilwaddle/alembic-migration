from sqlalchemy import (
    # Column,
    # Integer,
    # String,
    # Float,
    # Boolean,
    # Date,
    # Text,
    create_engine,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = "postgresql://postgres:2020@db:5432/migration_db"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
