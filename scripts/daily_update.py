"""
增量数据更新 CLI

功能：
  1. 补抓历史缺口（2025-01-01 至今的龙虎榜 + 席位 + K线）
  2. 每日收盘后增量更新（新龙虎榜 + 新K线）
  3. 重新计算席位评分并更新缓存

用法：
  # 完整补跑（2025-01-01 至今）
  python3 scripts/daily_update.py --catchup

  # 只更新最近N天
  python3 scripts/daily_update.py --days 7

  # 只更新今日
  python3 scripts/daily_update.py

  # 跳过K线更新（只更新龙虎榜）
  python3 scripts/daily_update.py --skip-kline
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger

CATCHUP_START = "20250101"   # 历史数据截止 2024-12-31，从此开始补


def get_date_range(days: int = None, start: str = None) -> tuple[str, str]:
    """返回 (start_str YYYYMMDD, end_str YYYYMMDD)"""
    today = datetime.now()
    end_str = today.strftime("%Y%m%d")
    if start:
        return start, end_str
    if days:
        start_dt = today - timedelta(days=days)
        return start_dt.strftime("%Y%m%d"), end_str
    # 默认：只今日
    return end_str, end_str


def update_lhb_data(start_date: str, end_date: str):
    """增量更新龙虎榜数据（akshare）"""
    from fetchers.lhb import fetch_lhb_list
    logger.info(f"更新龙虎榜: {start_date} ~ {end_date}")
    total = fetch_lhb_list(start_date=start_date, end_date=end_date)
    logger.success(f"龙虎榜更新完成，新增 {total} 条")
    return total


def update_kline_data(start_date: str, end_date: str):
    """增量更新K线数据"""
    from fetchers.kline import fetch_klines_for_lhb_stocks
    logger.info(f"更新K线: {start_date} ~ {end_date}")
    total = fetch_klines_for_lhb_stocks(start_date=start_date, end_date=end_date)
    logger.success(f"K线更新完成，新增 {total} 条")
    return total


def refresh_seat_ranking():
    """重新计算席位评分并更新CSV缓存"""
    from analysis.seat_winrate import calc_seat_winrate
    logger.info("刷新席位评分缓存...")
    df = calc_seat_winrate()
    os.makedirs("analysis", exist_ok=True)
    df.to_csv("analysis/seat_ranking.csv", encoding="utf-8-sig")
    logger.success(f"席位评分已更新: {len(df)} 个席位")


def main():
    parser = argparse.ArgumentParser(description="Whale Tracker 增量数据更新")
    parser.add_argument("--catchup",    action="store_true", help=f"补跑从 {CATCHUP_START} 至今的数据")
    parser.add_argument("--days",       type=int, default=None, help="更新最近N天数据")
    parser.add_argument("--skip-kline", action="store_true",    help="跳过K线更新")
    parser.add_argument("--skip-lhb",  action="store_true",    help="跳过龙虎榜更新")
    parser.add_argument("--only-refresh-seats", action="store_true", help="仅刷新席位评分")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("Whale Tracker 增量数据更新")
    logger.info("=" * 60)

    # 仅刷新席位
    if args.only_refresh_seats:
        refresh_seat_ranking()
        return

    # 确定日期范围
    if args.catchup:
        start_date, end_date = get_date_range(start=CATCHUP_START)
        logger.info(f"补跑模式: {start_date} ~ {end_date}")
    elif args.days:
        start_date, end_date = get_date_range(days=args.days)
        logger.info(f"近{args.days}天模式: {start_date} ~ {end_date}")
    else:
        start_date, end_date = get_date_range()
        logger.info(f"今日模式: {start_date}")

    # Step 1: 更新龙虎榜
    if not args.skip_lhb:
        try:
            update_lhb_data(start_date, end_date)
        except Exception as e:
            logger.error(f"龙虎榜更新失败: {e}")

    # Step 2: 更新K线
    if not args.skip_kline:
        try:
            update_kline_data(start_date, end_date)
        except Exception as e:
            logger.error(f"K线更新失败: {e}")

    # Step 3: 刷新席位评分
    refresh_seat_ranking()

    logger.info("=" * 60)
    logger.success("增量更新完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
