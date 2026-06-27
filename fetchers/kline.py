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


def _parse_days(days: list) -> list:
    """解析腾讯K线数组，返回标准格式行"""
    rows = []
    for d in days:
        try:
            rows.append({
                "date":        d[0],
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


def _extract_days(data: dict, symbol: str) -> list:
    """从腾讯API响应中提取K线数组，兼容各种嵌套格式"""
    raw_data = data.get("data", {})
    if not isinstance(raw_data, dict):
        return []
    stock_data = raw_data.get(symbol, {})
    if isinstance(stock_data, list):
        return stock_data
    elif isinstance(stock_data, dict):
        return stock_data.get("qfqday") or stock_data.get("day") or []
    return []


def _fetch_kline_tencent(code: str, start: str, end: str) -> list:
    """
    从腾讯证券拉取日K线（优先前复权，无数据则 fallback 不复权）。
    返回 list of dict，字段：date/open/close/high/low/volume/change_rate
    """
    symbol = _build_symbol(code)
    start_str = f"{start[:4]}-{start[4:6]}-{start[6:]}"
    end_str   = f"{end[:4]}-{end[4:6]}-{end[6:]}"
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

    # 优先前复权(qfq)，部分新股/北交所不支持则 fallback 到不复权
    for adj in ["qfq", ""]:
        var_name = f"kline_dayqfq_{code}" if adj else f"kline_day_{code}"
        params = {
            "_var": var_name,
            "param": f"{symbol},day,{start_str},{end_str},5000,{adj}"
        }
        resp = requests.get(url, params=params, timeout=15)
        text = resp.text
        json_str = text[text.index("=") + 1:]
        data = json.loads(json_str)

        days = _extract_days(data, symbol)
        if days:
            return _parse_days(days)

    return []  # 两种方式均无数据（真正退市/无法访问）


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
    all_codes = [r[0] for r in result]

    if limit:
        all_codes = all_codes[:limit]

    # 预过滤：只处理未完成的股票（跳过 status=done 的，保留 status=error 的）
    pending = [c for c in all_codes if not _is_done(f"kline:{c}")]
    done_before = len(all_codes) - len(pending)
    logger.info(f"K线采集：共 {len(all_codes)} 只股票，已完成 {done_before}，待采集 {len(pending)}（腾讯证券数据源）")

    if not pending:
        logger.info("全部已完成，跳过")
        return 0

    total_new = 0
    for i, code in enumerate(pending, 1):
        new = fetch_kline_single(code, start_date, end_date)
        total_new += new
        if new > 0:
            logger.success(f"  [{i}/{len(pending)}] {code} → +{new} 行")
        else:
            logger.debug(f"  [{i}/{len(pending)}] {code} → 0行（退市/无数据）")
        time.sleep(KLINE_SLEEP)
        if i % 200 == 0:
            pct = round((done_before + i) / len(all_codes) * 100, 1)
            logger.info(f"  进度 {pct}%，本次新增 {total_new} 条")

    logger.info(f"K线采集完成，累计新增 {total_new} 条")
    return total_new
