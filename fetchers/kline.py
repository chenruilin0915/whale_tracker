"""
日K线数据采集模块（腾讯证券数据源，香港服务器可用）

功能：
  fetch_klines_for_lhb_stocks() — 为龙虎榜中出现过的所有股票拉取日K线
  fetch_kline_single()          — 单只股票K线（供外部调用）

数据源：web.ifzq.gtimg.cn（腾讯证券），替代东方财富 push2his（香港不可达）
"""

import time
import json
from datetime import datetime
from typing import Optional

import requests
from loguru import logger
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import HISTORY_START, HISTORY_END, KLINE_SLEEP
from db.connection import get_session, get_engine
from db.models import FetchLog, LhbDaily, StockDaily


# ─────────────────────────────────────────────────────────────
# 腾讯K线接口
# ─────────────────────────────────────────────────────────────

def _build_symbol(code: str) -> str:
    """000001 → sz000001，600001 → sh600001"""
    if code.startswith("6"):
        return f"sh{code}"
    elif code.startswith("8") or code.startswith("4"):
        return f"bj{code}"
    else:
        return f"sz{code}"


def _fetch_kline_tencent(code: str, start: str, end: str) -> list:
    """
    从腾讯证券拉取前复权日K线。
    返回 list of dict，字段：date/open/close/high/low/volume/change_rate
    """
    symbol = _build_symbol(code)
    # 腾讯接口：start/end 格式 YYYY-MM-DD，count 给足够大的数
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "_var": f"kline_dayqfq_{code}",
        "param": f"{symbol},day,{start[:4]}-{start[4:6]}-{start[6:]},{end[:4]}-{end[4:6]}-{end[6:]},5000,qfq"
    }
    resp = requests.get(url, params=params, timeout=15)
    text = resp.text

    # 响应格式：kline_dayqfq_XXXXXX={...}
    json_str = text[text.index("=") + 1:]
    data = json.loads(json_str)

    # 取 qfqday 或 day（兼容不同返回格式）
    stock_data = data.get("data", {}).get(symbol, {})
    if isinstance(stock_data, list):
        days = stock_data          # 部分股票直接返回列表
    else:
        days = stock_data.get("qfqday") or stock_data.get("day") or []

    rows = []
    for d in days:
        # 格式：[date, open, close, high, low, volume, ?, ?, change_rate?, ...]
        try:
            rows.append({
                "date":        d[0],           # YYYY-MM-DD
                "open":        float(d[1]),
                "close":       float(d[2]),
                "high":        float(d[3]),
                "low":         float(d[4]),
                "volume":      float(d[5]),
                "amount":      None,
                "amplitude":   None,
                "change_rate": float(d[8]) if len(d) > 8 else None,
                "change_amt":  None,
                "turnover":    None,
            })
        except (IndexError, ValueError):
            continue
    return rows


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# 采集入口
# ─────────────────────────────────────────────────────────────

def fetch_kline_single(
    code: str,
    start_date: str = HISTORY_START,
    end_date: str = HISTORY_END,
) -> int:
    task_key = f"kline:{code}"
    if _is_done(task_key):
        return 0

    try:
        day_rows = _fetch_kline_tencent(code, start_date, end_date)
        if not day_rows:
            _mark_done(task_key, 0)
            return 0

        db_rows = [{"code": code, **r} for r in day_rows]

        engine = get_engine()
        with engine.begin() as conn:
            stmt = sqlite_insert(StockDaily).values(db_rows)
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
    with get_session() as s:
        result = s.query(LhbDaily.code).distinct().all()
    codes = [r[0] for r in result]

    if limit:
        codes = codes[:limit]

    logger.info(f"K线采集：共 {len(codes)} 只股票（腾讯证券数据源）")
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
