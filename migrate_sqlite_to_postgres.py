# migrate_sqlite_to_postgres.py
import os
from sqlalchemy import create_engine, MetaData, Table, text
from sqlalchemy.engine import Engine
from sqlalchemy.dialects.postgresql import insert as pg_insert

SQLITE_PATH = os.getenv("SQLITE_PATH", "./betreports.db")   # откуда читаем (при необходимости поменяй на bets.db)
PG_URL = os.getenv("DATABASE_URL") or ""                    # должен быть задан в окружении

def mask(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" in rest and ":" in rest.split("@", 1)[0]:
        creds, host = rest.split("@", 1)
        user = creds.split(":", 1)[0]
        return f"{scheme}://{user}:***@{host}"
    return url

def connect_sqlite(path: str) -> Engine:
    url = f"sqlite:///{path}"
    return create_engine(url, connect_args={"check_same_thread": False})

def connect_pg(url: str) -> Engine:
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)

def migrate(table_name: str = "bets"):
    if not PG_URL:
        raise RuntimeError("DATABASE_URL не задан")

    src = connect_sqlite(SQLITE_PATH)
    dst = connect_pg(PG_URL)

    print(f"[sqlite] {SQLITE_PATH}")
    print(f"[postgres] {mask(PG_URL)}")

    # Рефлексия схем
    src_meta = MetaData()
    dst_meta = MetaData()
    src_meta.reflect(bind=src, only=[table_name])
    dst_meta.reflect(bind=dst, only=[table_name])

    if table_name not in src_meta.tables:
        raise RuntimeError(f"В SQLite нет таблицы '{table_name}'")
    if table_name not in dst_meta.tables:
        raise RuntimeError(f"В Postgres нет таблицы '{table_name}'")

    src_tbl: Table = src_meta.tables[table_name]
    dst_tbl: Table = dst_meta.tables[table_name]

    src_cols = {c.name for c in src_tbl.columns}
    dst_cols = {c.name for c in dst_tbl.columns}
    common_cols = [c for c in dst_tbl.columns.keys() if c in src_cols]  # порядок как в целевой таблице

    if not common_cols:
        raise RuntimeError("Нет пересечений столбцов между SQLite и Postgres.")

    print(f"[cols] копируем поля: {common_cols}")

    # Читаем пачками и вставляем
    rows_copied = 0
    with src.connect() as sconn, dst.begin() as dconn:
        result = sconn.execute(text(f"SELECT * FROM {table_name}"))
        batch = []
        BATCH_SIZE = 1000

        for row in result.mappings():  # словари
            payload = {col: row.get(col) for col in common_cols}
            batch.append(payload)
            if len(batch) >= BATCH_SIZE:
                dconn.execute(dst_tbl.insert(), batch)
                rows_copied += len(batch)
                batch.clear()

        if batch:
            dconn.execute(dst_tbl.insert(), batch)
            rows_copied += len(batch)

    print(f"[done] скопировано строк: {rows_copied}")

if __name__ == "__main__":
    migrate("bets")  # если твоя таблица называется иначе — поменяй тут
