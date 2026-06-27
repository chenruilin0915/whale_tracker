"""
模拟盘交易引擎

职责：
  - 将信号写入 pending 持仓
  - 早盘：获取开盘价 → 确认买入 → status=open
  - 收盘：检查止损/止盈/到期 → 平仓 → status=closed
  - 计算当日及累计盈亏
"""

import math
import requests
from datetime import date, datetime
from typing import Optional

from loguru import logger
from sqlalchemy import and_

from config import (
    PAPER_CAPITAL, PAPER_MAX_POS,
    PAPER_STOP_LOSS, PAPER_TAKE_PROFIT, PAPER_MAX_HOLD
)
from db.connection import get_session
from db.models import PaperPosition

POSITION_SIZE = PAPER_CAPITAL // PAPER_MAX_POS   # 每仓金额，默认 20,000


# ─────────────────────────────────────────────────────────────
# 实时行情（腾讯证券）
# ─────────────────────────────────────────────────────────────

def _build_symbol(code: str) -> str:
    if code.startswith("6"):   return f"sh{code}"
    if code.startswith(("8","4")): return f"bj{code}"
    return f"sz{code}"


def fetch_realtime(codes: list[str]) -> dict[str, dict]:
    """
    批量获取实时行情（腾讯 qt.gtimg.cn）。
    返回: {code: {"price": float, "open": float, "high": float, "low": float, "name": str}}
    """
    if not codes:
        return {}
    symbols = ",".join(_build_symbol(c) for c in codes)
    url = f"https://qt.gtimg.cn/q={symbols}"
    try:
        resp = requests.get(url, timeout=10)
        result = {}
        for line in resp.text.strip().split("\n"):
            if "=" not in line:
                continue
            val = line.split("=")[1].strip().strip('";')
            parts = val.split("~")
            if len(parts) < 34:
                continue
            code_raw = parts[2]
            # normalize: sh600000 → 600000
            code = code_raw[-6:] if len(code_raw) >= 6 else code_raw
            try:
                result[code] = {
                    "name":  parts[1],
                    "price": float(parts[3]) if parts[3] else 0.0,
                    "open":  float(parts[5]) if parts[5] else 0.0,
                    "high":  float(parts[33]) if parts[33] else 0.0,
                    "low":   float(parts[34]) if parts[34] else 0.0,
                }
            except (ValueError, IndexError):
                continue
        return result
    except Exception as e:
        logger.warning(f"行情获取失败: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# 持仓操作
# ─────────────────────────────────────────────────────────────

def add_pending(signals, signal_date: date) -> int:
    """
    将当日信号写入 pending 状态持仓。
    已有 pending/open 的股票不重复添加（同一股票不重仓）。
    返回新增数量。
    """
    with get_session() as s:
        # 当前已有持仓的代码
        existing = {
            p.code for p in s.query(PaperPosition)
            .filter(PaperPosition.status.in_(["pending", "open"]))
            .all()
        }
        # 剩余仓位
        open_count = len([p for p in s.query(PaperPosition)
                          .filter(PaperPosition.status.in_(["pending", "open"])).all()])
        slots = PAPER_MAX_POS - open_count

        added = 0
        for _, row in signals.iterrows():
            if slots <= 0:
                logger.info(f"仓位已满（{PAPER_MAX_POS}仓），跳过剩余信号")
                break
            if row["code"] in existing:
                logger.debug(f"  {row['code']} 已有持仓，跳过")
                continue
            s.add(PaperPosition(
                code         = row["code"],
                name         = row["name"],
                signal_date  = signal_date,
                status       = "pending",
                signal_seat  = row.get("best_seat", ""),
                signal_score = float(row.get("score", 0)),
                created_at   = datetime.now().isoformat(),
            ))
            existing.add(row["code"])
            slots -= 1
            added += 1
            logger.success(f"  + 待买入: {row['code']} {row['name']}  席位: {row.get('best_seat','')[:20]}")

    logger.info(f"新增 {added} 个 pending 持仓")
    return added


def open_positions(trade_date: date) -> list[dict]:
    """
    早盘：将 pending 持仓以当日开盘价确认买入 → status=open。
    返回已开仓列表（用于推送）。
    """
    with get_session() as s:
        pending = s.query(PaperPosition).filter_by(status="pending").all()
        if not pending:
            logger.info("无 pending 持仓，跳过开仓")
            return []

        codes = [p.code for p in pending]
        quotes = fetch_realtime(codes)

        opened = []
        for pos in pending:
            q = quotes.get(pos.code)
            if not q or q["open"] <= 0:
                logger.warning(f"  {pos.code} 获取开盘价失败，保留 pending")
                continue

            open_price = q["open"]
            shares = math.floor(POSITION_SIZE / open_price / 100) * 100
            if shares <= 0:
                logger.warning(f"  {pos.code} 价格 {open_price} 过高，仓位不足100股，跳过")
                continue

            cost = round(open_price * shares, 2)
            pos.entry_date  = trade_date
            pos.entry_price = open_price
            pos.shares      = shares
            pos.cost        = cost
            pos.status      = "open"
            if not pos.name:
                pos.name = q.get("name", pos.code)

            opened.append({
                "code":  pos.code,
                "name":  pos.name or pos.code,
                "price": open_price,
                "shares": shares,
                "cost":  cost,
            })
            logger.success(
                f"  ✅ 开仓 {pos.code} {pos.name}  "
                f"开盘价: {open_price:.2f}  {shares}股  {cost:,.0f}元"
            )

    return opened


def check_exits(trade_date: date) -> tuple[list[dict], list[dict]]:
    """
    收盘：检查所有 open 持仓的止损/止盈/到期。
    返回 (closed_list, still_open_list)
    """
    with get_session() as s:
        positions = s.query(PaperPosition).filter_by(status="open").all()
        if not positions:
            return [], []

        codes = [p.code for p in positions]
        quotes = fetch_realtime(codes)

        closed = []
        still_open = []

        for pos in positions:
            q = quotes.get(pos.code)
            current_price = q["price"] if q and q["price"] > 0 else None

            if current_price is None:
                logger.warning(f"  {pos.code} 无法获取行情，保留持仓")
                still_open.append({
                    "code": pos.code, "name": pos.name or pos.code,
                    "hold_days": (trade_date - pos.entry_date).days if pos.entry_date else "?",
                })
                continue

            hold_days = (trade_date - pos.entry_date).days if pos.entry_date else 0
            ret = (current_price - pos.entry_price) / pos.entry_price

            # 判断退出条件（优先级：止损 > 止盈 > 到期）
            exit_reason = None
            if ret <= PAPER_STOP_LOSS:
                exit_reason = "stop_loss"
            elif ret >= PAPER_TAKE_PROFIT:
                exit_reason = "take_profit"
            elif hold_days >= PAPER_MAX_HOLD:
                exit_reason = "max_hold"

            if exit_reason:
                pnl     = round((current_price - pos.entry_price) * pos.shares, 2)
                pnl_pct = round(ret * 100, 2)
                pos.exit_date   = trade_date
                pos.exit_price  = current_price
                pos.exit_reason = exit_reason
                pos.pnl         = pnl
                pos.pnl_pct     = pnl_pct
                pos.status      = "closed"

                closed.append({
                    "code": pos.code, "name": pos.name or pos.code,
                    "entry": pos.entry_price, "exit_price": current_price,
                    "pnl": pnl, "pnl_pct": pnl_pct,
                    "exit_reason": exit_reason, "hold_days": hold_days,
                })
                label = {"stop_loss":"🛑止损","take_profit":"🎯止盈","max_hold":"⏰到期"}[exit_reason]
                logger.success(
                    f"  {label} {pos.code} {pos.name}  "
                    f"{pos.entry_price:.2f}→{current_price:.2f}  "
                    f"{pnl_pct:+.1f}% ({pnl:+,.0f}元)"
                )
            else:
                float_pct = round(ret * 100, 2)
                still_open.append({
                    "code": pos.code, "name": pos.name or pos.code,
                    "hold_days": hold_days,
                    "float_pct": float_pct,
                    "entry_price": pos.entry_price,
                    "current_price": current_price,
                })
                logger.info(
                    f"  📌 持仓 {pos.code} {pos.name}  "
                    f"持{hold_days}天  浮盈: {float_pct:+.1f}%"
                )

    return closed, still_open


def get_total_pnl() -> dict:
    """统计累计盈亏"""
    with get_session() as s:
        closed = s.query(PaperPosition).filter_by(status="closed").all()
        total_pnl   = sum(p.pnl or 0 for p in closed)
        win_count   = sum(1 for p in closed if (p.pnl or 0) > 0)
        total_count = len(closed)
        win_rate    = win_count / total_count if total_count > 0 else 0
    return {
        "total_pnl":   round(total_pnl, 2),
        "total_trades": total_count,
        "win_count":   win_count,
        "win_rate":    round(win_rate, 3),
    }
