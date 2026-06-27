"""
早盘开仓脚本 — 每日 09:35 运行

功能：
  1. 将昨晚生成的 pending 持仓以今日开盘价确认买入
  2. 推送开仓通知到手机

用法：
  python3 scripts/morning_open.py
  python3 scripts/morning_open.py --date 20260627   # 指定日期（补跑）
"""
import argparse
import os
import sys
from datetime import datetime, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from trading.paper_trader import open_positions
from utils.notify import push_open, push


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=None, help="交易日期 YYYYMMDD")
    args = parser.parse_args()

    trade_date = (
        datetime.strptime(args.date, "%Y%m%d").date()
        if args.date else date.today()
    )

    logger.info(f"{'='*50}")
    logger.info(f"早盘开仓  {trade_date}")
    logger.info(f"{'='*50}")

    opened = open_positions(trade_date)

    if not opened:
        logger.info("今日无需开仓")
        push("🐋 今日无开仓", f"{trade_date} 无待买入持仓")
        return

    for p in opened:
        push_open(p["code"], p["name"], p["price"], p["shares"], p["cost"])

    logger.success(f"开仓完成: {len(opened)} 只")


if __name__ == "__main__":
    main()
