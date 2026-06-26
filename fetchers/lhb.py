"""
龙虎榜数据采集模块

功能：
  1. fetch_lhb_list()      — 批量抓取龙虎榜列表（按月），写入 lhb_daily
  2. fetch_lhb_seats()     — 抓取席位明细，写入 lhb_seat_detail
  3. classify_seat_type()  — 判断席位类型（机构/游资/北向/未知）
"""

import time
from datetime import datetime, date
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import LHB_LIST_SLEEP, LHB_DETAIL_SLEEP
from db.connection import get_session, get_engine
from db.models import FetchLog, LhbDaily, LhbSeatDetail


# ─────────────────────────────────────────────────────────────
# 席位类型识别
# ─────────────────────────────────────────────────────────────

# 机构专用席位关键词（东财/同花顺认定）
_INSTITUTION_KEYWORDS = [
    "机构专用", "QFII", "沪股通", "深股通", "北向"
]

def classify_seat_type(seat_name: str) -> str:
    """
    根据席位名称粗略判断类型：
      机构  — 含"机构专用"等关键词
      北向  — 沪/深股通
      游资  — 普通营业部（非机构）
    """
    if not seat_name:
        return "未知"
    for kw in _INSTITUTION_KEYWORDS:
        if kw in seat_name:
            if "股通" in seat_name or "北向" in seat_name:
                return "北向"
            return "机构"
    return "游资"


# ─────────────────────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────────────────────

def _is_done(task_key: str) -> bool:
    """检查某个采集任务是否已完成（断点续传）"""
    with get_session() as s:
        row = s.query(FetchLog).filter_by(task_key=task_key, status="done").first()
        return row is not None


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


def _month_ranges(start: str, end: str):
    """
    生成月份区间列表，例如 ('20200101','20241231') →
    [('20200101','20200131'), ('20200201','20200229'), ...]
    """
    from calendar import monthrange
    s = datetime.strptime(start, "%Y%m%d")
    e = datetime.strptime(end, "%Y%m%d")
    cur = date(s.year, s.month, 1)
    end_d = date(e.year, e.month, 1)
    while cur <= end_d:
        _, last_day = monthrange(cur.year, cur.month)
        month_end = date(cur.year, cur.month, last_day)
        # 不超过 end
        actual_end = min(month_end, e.date() if hasattr(e, 'date') else e)
        yield (
            cur.strftime("%Y%m%d"),
            actual_end.strftime("%Y%m%d")
        )
        # 下个月1号
        if cur.month == 12:
            cur = date(cur.year + 1, 1, 1)
        else:
            cur = date(cur.year, cur.month + 1, 1)


# ─────────────────────────────────────────────────────────────
# 1. 龙虎榜列表
# ─────────────────────────────────────────────────────────────

def fetch_lhb_list(start_date: str, end_date: str) -> int:
    """
    抓取龙虎榜列表（按月分批），写入 lhb_daily 表。
    已采集的月份自动跳过（断点续传）。

    返回：新写入的总行数
    """
    total_new = 0
    engine = get_engine()
    months = list(_month_ranges(start_date, end_date))
    logger.info(f"龙虎榜列表：共 {len(months)} 个月份待检查")

    for m_start, m_end in months:
        task_key = f"lhb_list:{m_start[:6]}"
        if _is_done(task_key):
            logger.debug(f"  跳过（已完成）: {m_start[:6]}")
            continue

        logger.info(f"  采集: {m_start} ~ {m_end}")
        try:
            df = ak.stock_lhb_detail_em(start_date=m_start, end_date=m_end)
            if df is None or df.empty:
                _mark_done(task_key, 0)
                time.sleep(LHB_LIST_SLEEP)
                continue

            # 字段映射到模型
            rows = []
            for _, r in df.iterrows():
                rows.append({
                    "code":        str(r["代码"]).zfill(6),
                    "name":        r.get("名称"),
                    "date":        r["上榜日"],
                    "close_price": r.get("收盘价"),
                    "change_rate": r.get("涨跌幅"),
                    "net_buy_amt": r.get("龙虎榜净买额"),
                    "buy_amt":     r.get("龙虎榜买入额"),
                    "sell_amt":    r.get("龙虎榜卖出额"),
                    "deal_amt":    r.get("龙虎榜成交额"),
                    "total_amt":   r.get("市场总成交额"),
                    "net_ratio":   r.get("净买额占总成交比"),
                    "deal_ratio":  r.get("成交额占总成交比"),
                    "turnover":    r.get("换手率"),
                    "free_cap":    r.get("流通市值"),
                    "reason":      r.get("上榜原因"),
                    "d1_ret":      r.get("上榜后1日"),
                    "d2_ret":      r.get("上榜后2日"),
                    "d5_ret":      r.get("上榜后5日"),
                    "d10_ret":     r.get("上榜后10日"),
                })

            # UPSERT（忽略重复）
            with engine.begin() as conn:
                stmt = sqlite_insert(LhbDaily).values(rows)
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["code", "date"]
                )
                result = conn.execute(stmt)
                new_rows = result.rowcount

            total_new += new_rows
            _mark_done(task_key, new_rows)
            logger.success(f"    ✓ {len(rows)} 条数据，新增 {new_rows} 条")

        except Exception as e:
            logger.error(f"    ✗ 失败: {e}")
            _mark_error(task_key, str(e))

        time.sleep(LHB_LIST_SLEEP)

    logger.info(f"龙虎榜列表采集完成，累计新增 {total_new} 条")
    return total_new


# ─────────────────────────────────────────────────────────────
# 2. 席位明细
# ─────────────────────────────────────────────────────────────

def fetch_lhb_seats(limit: Optional[int] = None) -> int:
    """
    对 lhb_daily 中每条记录，抓取买方+卖方席位明细。
    已采集的跳过（断点续传）。

    Args:
        limit: 限制本次最多采集 N 条记录（调试用），None 表示全量

    返回：新写入的总席位数
    """
    engine = get_engine()

    # 查询所有需要采集席位的 (code, date) 组合
    with get_session() as s:
        records = s.query(LhbDaily.code, LhbDaily.date).all()

    if limit:
        records = records[:limit]

    logger.info(f"席位明细：共 {len(records)} 条记录待检查")
    total_new = 0

    for code, dt in records:
        date_str = dt.strftime("%Y%m%d") if hasattr(dt, "strftime") else str(dt).replace("-", "")
        task_key = f"lhb_seat:{code}:{date_str}"

        if _is_done(task_key):
            continue

        rows = []
        has_error = False

        for direction in ["买入", "卖出"]:
            try:
                df = ak.stock_lhb_stock_detail_em(
                    symbol=code, date=date_str, flag=direction
                )
                if df is None or df.empty:
                    continue

                for _, r in df.iterrows():
                    seat_name = r.get("交易营业部名称", "")
                    rows.append({
                        "code":       code,
                        "date":       dt,
                        "direction":  direction,
                        "seat_name":  seat_name,
                        "seat_type":  classify_seat_type(seat_name),
                        "buy_amt":    r.get("买入金额"),
                        "buy_ratio":  r.get("买入金额-占总成交比例"),
                        "sell_amt":   r.get("卖出金额"),
                        "sell_ratio": r.get("卖出金额-占总成交比例"),
                        "net_amt":    r.get("净额"),
                    })

                time.sleep(LHB_DETAIL_SLEEP / 2)  # 买卖之间短暂间隔

            except Exception as e:
                logger.warning(f"  席位 {code} {date_str} {direction}: {e}")
                has_error = True
                break

        if has_error:
            _mark_error(task_key, "fetch failed")
            time.sleep(LHB_DETAIL_SLEEP * 2)
            continue

        if rows:
            with engine.begin() as conn:
                conn.execute(LhbSeatDetail.__table__.insert(), rows)
            total_new += len(rows)

        _mark_done(task_key, len(rows))
        time.sleep(LHB_DETAIL_SLEEP)

    logger.info(f"席位明细采集完成，累计新增 {total_new} 条")
    return total_new
