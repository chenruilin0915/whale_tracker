"""
收盘脚本 — 每日 15:35 运行

执行顺序：
  1. 检查持仓：触发止损/止盈/到期的标记为 pending_exit（明日开盘卖）
  2. 生成今日信号：写入 pending（明日开盘买）
  3. 推送每日汇总：浮盈情况 + 明日操作预告 + 新信号

用法：
  python3 scripts/evening_check.py
  python3 scripts/evening_check.py --date 20260626
  python3 scripts/evening_check.py --skip-signal
"""
import argparse
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from trading.paper_trader import check_exits, add_pending, get_total_pnl
from analysis.signal_filter import generate_signals
from utils.notify import push_signals, push_daily_summary, push


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date",        default=None,        help="交易日期 YYYYMMDD")
    parser.add_argument("--skip-signal", action="store_true", help="跳过信号生成")
    parser.add_argument("--skip-notify", action="store_true", help="跳过推送")
    args = parser.parse_args()

    trade_date = (
        datetime.strptime(args.date, "%Y%m%d").date()
        if args.date else date.today()
    )
    trade_date_str = trade_date.strftime("%Y%m%d")

    logger.info(f"{'='*55}")
    logger.info(f"收盘检查  {trade_date}")
    logger.info(f"{'='*55}")

    # ── Step 1: 检查持仓，标记 pending_exit ─────────────────
    logger.info("Step 1: 检查止损/止盈/到期...")
    pending_exit, still_open = check_exits(trade_date)

    # ── Step 2: 生成今日信号 ─────────────────────────────────
    new_signals_count = 0
    signals = None
    if not args.skip_signal:
        logger.info("Step 2: 生成今日信号...")
        signals = generate_signals(trade_date=trade_date_str)
        if signals is not None and not signals.empty:
            os.makedirs("signals", exist_ok=True)
            signals.to_csv(
                f"signals/signal_{trade_date_str}.csv",
                index=False, encoding="utf-8-sig"
            )
            new_signals_count = add_pending(signals, trade_date)

    # ── Step 3: 汇总推送 ─────────────────────────────────────
    stats = get_total_pnl()

    logger.info(f"{'='*55}")
    logger.info(f"持仓中: {len(still_open)} 只  明日平仓预告: {len(pending_exit)} 只  新信号: {new_signals_count} 只")
    logger.info(f"累计盈亏: {stats['total_pnl']:+,.0f} 元  胜率: {stats['win_rate']:.0%}  共{stats['total_trades']}笔")
    logger.info(f"{'='*55}")

    if not args.skip_notify:
        # 推送新信号
        if signals is not None:
            push_signals(signals, trade_date_str)

        # 推送每日汇总（含明日操作预告）
        _push_evening_summary(trade_date_str, still_open, pending_exit, stats)


def _push_evening_summary(date_str, still_open, pending_exit, stats):
    from utils.notify import push
    lines = [f"**{date_str} 收盘汇总**\n"]

    if pending_exit:
        lines.append("### 🔔 明日开盘操作")
        for p in pending_exit:
            label = {"stop_loss":"🛑止损","take_profit":"🎯止盈","max_hold":"⏰到期"}.get(
                p["exit_reason"], "平仓")
            lines.append(
                f"{label} **{p['code']} {p['name']}**  "
                f"收盘浮{p['float_pct']:+.1f}%  → 明日开盘卖"
            )

    if still_open:
        lines.append("\n### 📌 持仓中")
        for p in still_open:
            fp = f"{p['float_pct']:+.1f}%" if p.get("float_pct") is not None else "—"
            lines.append(f"{p['code']} {p['name']}  持{p['hold_days']}天  浮{fp}")

    lines.append(
        f"\n**累计**: {stats['total_pnl']:+,.0f}元  "
        f"胜率 {stats['win_rate']:.0%}  共{stats['total_trades']}笔"
    )

    push(f"🐋 收盘 {date_str}", "\n".join(lines))


if __name__ == "__main__":
    main()
