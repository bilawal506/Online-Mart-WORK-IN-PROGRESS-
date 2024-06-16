from typing import Optional
from sqlmodel import SQLModel, Field, create_engine, Session
from . import settings

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str
    password: str
    phone_number: int
    email: str
    role: str  # Add a role attribute (e.g., 'admin' or 'user')

connection_string = str(settings.DATABASE_URL).replace("postgresql", "postgresql+psycopg")

engine = create_engine(connection_string, connect_args={}, pool_recycle=300)

def get_session():
    with Session(engine) as session:
        yield session
