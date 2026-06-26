"""
数据库连接与 Session 管理
"""
from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from config import DB_URL

_engine = create_engine(DB_URL, echo=False, connect_args={"check_same_thread": False})
_SessionFactory = sessionmaker(bind=_engine, autoflush=False, autocommit=False)


@contextmanager
def get_session() -> Session:
    """上下文管理器，自动提交/回滚"""
    session = _SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return _engine
