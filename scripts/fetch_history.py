"""
历史数据全量采集脚本
用法：python scripts/fetch_history.py [--step lhb|seats|kline|all]

流程：
  Step 1  lhb   — 抓取龙虎榜列表（约5分钟，按月分批，可断点续传）
  Step 2  seats — 抓取席位明细（耗时较长，几小时，可断点续传）
  Step 3  kline — 抓取K线数据（几十分钟，可断点续传）
"""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config import HISTORY_START, HISTORY_END, DB_URL
from db.models import init_db
from fetchers.lhb import fetch_lhb_list, fetch_lhb_seats
from fetchers.kline import fetch_klines_for_lhb_stocks


def main():
    parser = argparse.ArgumentParser(description="历史数据采集")
    parser.add_argument(
        "--step",
        choices=["lhb", "seats", "kline", "all"],
        default="all",
        help="指定采集步骤（默认 all = 依次执行全部）"
    )
    parser.add_argument(
        "--start", default=HISTORY_START, help=f"开始日期，默认 {HISTORY_START}"
    )
    parser.add_argument(
        "--end", default=HISTORY_END, help=f"结束日期，默认 {HISTORY_END}"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="限制采集数量（调试用，seats/kline 有效）"
    )
    args = parser.parse_args()

    # 确保数据库已初始化
    init_db(DB_URL)

    if args.step in ("lhb", "all"):
        logger.info("=" * 50)
        logger.info("Step 1：龙虎榜列表")
        logger.info("=" * 50)
        n = fetch_lhb_list(args.start, args.end)
        logger.info(f"完成，共写入 {n} 条")

    if args.step in ("seats", "all"):
        logger.info("=" * 50)
        logger.info("Step 2：席位明细")
        logger.info("提示：此步骤耗时较长（数小时），可随时 Ctrl+C 中断，下次自动续传")
        logger.info("=" * 50)
        n = fetch_lhb_seats(limit=args.limit)
        logger.info(f"完成，共写入 {n} 条")

    if args.step in ("kline", "all"):
        logger.info("=" * 50)
        logger.info("Step 3：日K线")
        logger.info("=" * 50)
        n = fetch_klines_for_lhb_stocks(args.start, args.end, limit=args.limit)
        logger.info(f"完成，共写入 {n} 条")

    logger.info("全部采集完成 ✓")


if __name__ == "__main__":
    main()
