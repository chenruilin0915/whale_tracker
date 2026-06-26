"""
日K线数据采集模块

功能：
  fetch_klines_for_lhb_stocks() — 为龙虎榜中出现过的所有股票拉取日K线
  fetch_kline_single()          — 单只股票K线（供外部调用）
"""

import time
from datetime import datetime
from typing import Optional

import akshare as ak
from loguru import logger
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import HISTORY_START, HISTORY_END, KLINE_SLEEP
from db.connection import get_session, get_engine
from db.models import FetchLog, LhbDaily, StockDaily


def _is_done(task_key: str) -> bool:
    with get_session() as s:
        return s.query(FetchLog).filter_by(task_key=task_key, status="done").first() is not None


def _mark_done(task_key: str, rows: int = 0) -> None:
    with get_session() as s:
        log = s.query(FetchLog).filter_by(task_key=task_key).first()
        if log:
            log.status = "done"
            log.rows = rows
            log.fetched_at = datetime.now().isoformat()
        else:
            s.add(FetchLog(
                task_key=task_key,
                status="done",
                rows=rows,
                fetched_at=datetime.now().isoformat()
            ))


def _mark_error(task_key: str, msg: str) -> None:
    with get_session() as s:
        log = s.query(FetchLog).filter_by(task_key=task_key).first()
        if log:
            log.status = "error"
            log.error_msg = str(msg)[:500]
        else:
            s.add(FetchLog(
                task_key=task_key,
                status="error",
                error_msg=str(msg)[:500],
                fetched_at=datetime.now().isoformat()
            ))


def fetch_kline_single(
    code: str,
    start_date: str = HISTORY_START,
    end_date: str = HISTORY_END,
    adjust: str = "qfq",
) -> int:
    """
    拉取单只股票日K线并写入 stock_daily。
    返回新增行数。
    """
    task_key = f"kline:{code}"
    if _is_done(task_key):
        return 0

    try:
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        if df is None or df.empty:
            _mark_done(task_key, 0)
            return 0

        rows = []
        for _, r in df.iterrows():
            rows.append({
                "code":        code,
                "date":        r["日期"],
                "open":        r.get("开盘"),
                "close":       r.get("收盘"),
                "high":        r.get("最高"),
                "low":         r.get("最低"),
                "volume":      r.get("成交量"),
                "amount":      r.get("成交额"),
                "amplitude":   r.get("振幅"),
                "change_rate": r.get("涨跌幅"),
                "change_amt":  r.get("涨跌额"),
                "turnover":    r.get("换手率"),
            })

        engine = get_engine()
        with engine.begin() as conn:
            stmt = sqlite_insert(StockDaily).values(rows)
            stmt = stmt.on_conflict_do_nothing(index_elements=["code", "date"])
            result = conn.execute(stmt)
            new_rows = result.rowcount

        _mark_done(task_key, new_rows)
        return new_rows

    except Exception as e:
        logger.warning(f"  K线 {code} 失败: {e}")
        _mark_error(task_key, str(e))
        return 0


def fetch_klines_for_lhb_stocks(
    start_date: str = HISTORY_START,
    end_date: str = HISTORY_END,
    limit: Optional[int] = None,
) -> int:
    """
    从 lhb_daily 中取出所有出现过的股票代码，
    逐一拉取日K线写入 stock_daily。

    Args:
        limit: 限制本次处理的股票数（调试用）
    """
    with get_session() as s:
        result = s.query(LhbDaily.code).distinct().all()
    codes = [r[0] for r in result]

    if limit:
        codes = codes[:limit]

    logger.info(f"K线采集：共 {len(codes)} 只股票")
    total_new = 0

    for i, code in enumerate(codes, 1):
        new = fetch_kline_single(code, start_date, end_date)
        total_new += new
        if new > 0:
            logger.success(f"  [{i}/{len(codes)}] {code} → +{new} 行")
        else:
            logger.debug(f"  [{i}/{len(codes)}] {code} → 跳过")
        time.sleep(KLINE_SLEEP)

    logger.info(f"K线采集完成，累计新增 {total_new} 条")
    return total_new
