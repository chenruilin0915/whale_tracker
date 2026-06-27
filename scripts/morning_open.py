"""
早盘脚本 — 每日 09:35 运行

执行顺序：
  1. 平仓：将昨晚标记的 pending_exit 以今日开盘价卖出 → 推送卖出通知
  2. 开仓：将 pending 信号以今日开盘价买入 → 推送买入通知

用法：
  python3 scripts/morning_open.py
  python3 scripts/morning_open.py --date 20260630
"""
import argparse
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from trading.paper_trader import execute_exits, open_positions
from utils.notify import push_open, push_close, push


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="交易日期 YYYYMMDD")
    args = parser.parse_args()

    trade_date = (
        datetime.strptime(args.date, "%Y%m%d").date()
        if args.date else date.today()
    )

    logger.info(f"{'='*50}")
    logger.info(f"早盘操作  {trade_date}")
    logger.info(f"{'='*50}")

    # ── Step 1: 执行平仓（昨日触发的止损/止盈/到期）──────────
    closed = execute_exits(trade_date)
    for p in closed:
        push_close(
            p["code"], p["name"],
            p["entry"], p["exit_price"],
            p["pnl"],   p["pnl_pct"],
            p["exit_reason"],
        )

    # ── Step 2: 执行开仓（昨日生成的新信号）────────────────────
    opened = open_positions(trade_date)
    for p in opened:
        push_open(p["code"], p["name"], p["price"], p["shares"], p["cost"])

    # ── 无操作时静默推送 ─────────────────────────────────────
    if not closed and not opened:
        logger.info("今日无开仓/平仓操作")
        push("🐋 今日无操作", f"{trade_date}  无待执行指令")
        return

    total = len(closed) + len(opened)
    logger.success(f"早盘完成: 平仓 {len(closed)} 只 | 开仓 {len(opened)} 只")


if __name__ == "__main__":
    main()
