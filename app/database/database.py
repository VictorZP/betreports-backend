from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv(override=False)

def _build_db_url() -> str:
    # 1) Пробуем DATABASE_URL из окружения
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url

    # 2) Railway может класть компоненты по отдельности
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST")
    db   = os.getenv("PGDATABASE") or os.getenv("POSTGRES_DB") or os.getenv("POSTGRES_DATABASE")
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER")
    pwd  = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD")
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"

    if host and db and user and pwd:
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"

    # 3) Ничего не нашли — пусть упадёт с понятным текстом
    raise RuntimeError(
        "DATABASE_URL is not set. In Railway set backend → Variables → DATABASE_URL "
        "as a Reference to Postgres → DATABASE_URL."
    )

DATABASE_URL = _build_db_url()

# --- только для отладки ---
safe = DATABASE_URL
if "@" in safe:
    scheme, rest = safe.split("://", 1)
    _, host = rest.split("@", 1)
    safe = f"{scheme}://***:***@{host}"
print(f"[database] Using {safe}")
# --- конец отладки ---

# Движок
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, pool_pre_ping=True)
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
