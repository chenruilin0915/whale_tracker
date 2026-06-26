"""
数据库状态检查脚本
用法：python scripts/check_db.py

输出数据库中各表的记录数、时间范围、采集进度等摘要信息。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func, text
from db.connection import get_session
from db.models import LhbDaily, LhbSeatDetail, StockDaily, FetchLog


def main():
    with get_session() as s:
        print("\n" + "=" * 55)
        print("  数据库状态报告")
        print("=" * 55)

        # lhb_daily
        total_lhb = s.query(func.count(LhbDaily.id)).scalar()
        if total_lhb > 0:
            min_date = s.query(func.min(LhbDaily.date)).scalar()
            max_date = s.query(func.max(LhbDaily.date)).scalar()
            stocks   = s.query(func.count(func.distinct(LhbDaily.code))).scalar()
            print(f"\n【龙虎榜列表】lhb_daily")
            print(f"  记录数：{total_lhb:,}")
            print(f"  日期范围：{min_date} ~ {max_date}")
            print(f"  涉及股票：{stocks} 只")
        else:
            print(f"\n【龙虎榜列表】lhb_daily — 暂无数据")

        # lhb_seat_detail
        total_seats = s.query(func.count(LhbSeatDetail.id)).scalar()
        if total_seats > 0:
            top_seats = (
                s.query(LhbSeatDetail.seat_name, func.count().label("cnt"))
                .filter(LhbSeatDetail.direction == "买入")
                .group_by(LhbSeatDetail.seat_name)
                .order_by(func.count().desc())
                .limit(5)
                .all()
            )
            print(f"\n【席位明细】lhb_seat_detail")
            print(f"  记录数：{total_seats:,}")
            print(f"  买方出现最多的席位（Top 5）：")
            for seat, cnt in top_seats:
                print(f"    {seat or '未知':40s} {cnt:4d} 次")
        else:
            print(f"\n【席位明细】lhb_seat_detail — 暂无数据")

        # stock_daily
        total_kline = s.query(func.count(StockDaily.id)).scalar()
        if total_kline > 0:
            kline_stocks = s.query(func.count(func.distinct(StockDaily.code))).scalar()
            print(f"\n【日K线】stock_daily")
            print(f"  记录数：{total_kline:,}")
            print(f"  覆盖股票：{kline_stocks} 只")
        else:
            print(f"\n【日K线】stock_daily — 暂无数据")

        # fetch_log 进度
        done  = s.query(func.count(FetchLog.id)).filter_by(status="done").scalar()
        error = s.query(func.count(FetchLog.id)).filter_by(status="error").scalar()
        print(f"\n【采集进度】fetch_log")
        print(f"  已完成：{done:,} 个任务")
        print(f"  失败：  {error:,} 个任务")

        print("\n" + "=" * 55 + "\n")


if __name__ == "__main__":
    main()
