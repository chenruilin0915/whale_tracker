"""
每日信号生成 CLI

用法：
  # 生成今日（或最近交易日）信号
  python3 scripts/daily_signal.py

  # 指定日期（回测/补跑）
  python3 scripts/daily_signal.py --date 20250620

  # 调整阈值
  python3 scripts/daily_signal.py --min-winrate 0.62 --min-score 0.72

  # 仅显示，不保存CSV
  python3 scripts/daily_signal.py --no-save
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

from analysis.signal_filter import (
    generate_signals,
    format_signal_report,
    MIN_SEAT_WIN_RATE,
    MIN_SEAT_SCORE,
)


def main():
    parser = argparse.ArgumentParser(description="Whale Tracker 每日信号生成")
    parser.add_argument("--date",         default=None,               help="交易日期 YYYYMMDD，默认今日")
    parser.add_argument("--min-winrate",  type=float, default=MIN_SEAT_WIN_RATE, help="席位5日胜率门槛")
    parser.add_argument("--min-score",    type=float, default=MIN_SEAT_SCORE,    help="席位综合评分门槛")
    parser.add_argument("--no-save",      action="store_true",        help="不保存CSV")
    args = parser.parse_args()

    trade_date = args.date or datetime.now().strftime("%Y%m%d")

    # 动态覆盖阈值
    import analysis.signal_filter as sf
    sf.MIN_SEAT_WIN_RATE = args.min_winrate
    sf.MIN_SEAT_SCORE    = args.min_score

    # 生成信号
    signals = generate_signals(trade_date=trade_date)

    # 打印报告
    report = format_signal_report(signals, trade_date)
    print(report)

    if signals.empty:
        return

    # 保存结果
    if not args.no_save:
        out_dir = "signals"
        os.makedirs(out_dir, exist_ok=True)
        out_path = f"{out_dir}/signal_{trade_date}.csv"
        signals.to_csv(out_path, index=False, encoding="utf-8-sig")
        logger.success(f"信号已保存: {out_path}")


if __name__ == "__main__":
    main()
