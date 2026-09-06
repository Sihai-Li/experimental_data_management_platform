from functools import lru_cache
from sqlalchemy import create_engine
from app.config import get_settings


@lru_cache
def get_engine():
    return create_engine(get_settings().database_url, pool_pre_ping=True, connect_args={"connect_timeout": 3})
