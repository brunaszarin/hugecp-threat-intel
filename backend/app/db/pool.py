from psycopg_pool import ConnectionPool

from app.core.config import settings


def create_pool() -> ConnectionPool:
    # open=False: o pool só abre no startup da aplicação (lifespan), não no import.
    # timeout=5: sem banco, a API responde erro em 5s em vez de travar 30s.
    return ConnectionPool(settings.database_url, min_size=1, max_size=10, timeout=5, open=False)
