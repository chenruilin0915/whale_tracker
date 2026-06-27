"""
收盘检查脚本 — 每日 15:35 运行

功能：
  1. 检查持仓中的止损/止盈/到期，自动平仓
  2. 生成今日信号（下一交易日 pending 持仓）
  3. 推送每日汇总 + 新信号到手机

用法：
  python3 scripts/evening_check.py
  python3 scripts/evening_check.py --date 20260626   # 指定日期（回测/补跑）
  python3 scripts/evening_check.py --skip-signal     # 只检查持仓，不生成新信号
"""
import argparse
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from trading.paper_trader import (
    check_exits, add_pending, get_total_pnl
)
from analysis.signal_filter import generate_signals
from utils.notify import (
    push_close, push_signals, push_daily_summary, push
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",         default=None,          help="交易日期 YYYYMMDD")
    parser.add_argument("--skip-signal",  action="store_true",   help="跳过信号生成")
    parser.add_argument("--skip-notify",  action="store_true",   help="跳过推送（调试用）")
    args = parser.parse_args()

    trade_date = (
        datetime.strptime(args.date, "%Y%m%d").date()
        if args.date else date.today()
    )
    trade_date_str = trade_date.strftime("%Y%m%d")

    logger.info(f"{'='*55}")
    logger.info(f"收盘检查  {trade_date}")
    logger.info(f"{'='*55}")

    # ── Step 1: 检查持仓退出 ─────────────────────────────────
    logger.info("Step 1: 检查止损/止盈/到期...")
    closed, still_open = check_exits(trade_date)

    # 逐条推送平仓
    if not args.skip_notify:
        for p in closed:
            push_close(
                p["code"], p["name"],
                p["entry"], p["exit_price"],
                p["pnl"],   p["pnl_pct"],
                p["exit_reason"],
            )

    # ── Step 2: 生成今日信号（供明日开仓）───────────────────
    new_signals_count = 0
    if not args.skip_signal:
        logger.info("Step 2: 生成今日信号...")
        signals = generate_signals(trade_date=trade_date_str)

        if not signals.empty:
            # 保存信号CSV
            os.makedirs("signals", exist_ok=True)
            signals.to_csv(
                f"signals/signal_{trade_date_str}.csv",
                index=False, encoding="utf-8-sig"
            )
            # 写入 pending 持仓
            new_signals_count = add_pending(signals, trade_date)

        if not args.skip_notify:
            push_signals(signals, trade_date_str)
    else:
        signals = None

    # ── Step 3: 每日汇总推送 ─────────────────────────────────
    stats = get_total_pnl()
    today_pnl = sum(p["pnl"] for p in closed)

    logger.info(f"{'='*55}")
    logger.info(f"今日平仓: {len(closed)} 笔  今日盈亏: {today_pnl:+,.0f} 元")
    logger.info(f"累计盈亏: {stats['total_pnl']:+,.0f} 元  "
                f"胜率: {stats['win_rate']:.0%}  共 {stats['total_trades']} 笔")
    logger.info(f"持仓中: {len(still_open)} 只  新信号: {new_signals_count} 只")
    logger.info(f"{'='*55}")

    if not args.skip_notify:
        push_daily_summary(trade_date_str, still_open, closed, today_pnl)


if __name__ == "__main__":
    main()
