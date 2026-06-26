"""
初始化数据库：创建所有表结构
用法：python scripts/init_db.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DB_URL
from db.models import init_db

if __name__ == "__main__":
    init_db(DB_URL)
