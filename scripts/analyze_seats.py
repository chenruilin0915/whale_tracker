"""
席位胜率分析 CLI

用法：
  python3 scripts/analyze_seats.py               # 标准分析，输出CSV
  python3 scripts/analyze_seats.py --top 20      # 只显示Top20
  python3 scripts/analyze_seats.py --min-records 50
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analysis.seat_winrate import calc_seat_winrate, filter_high_quality
from loguru import logger
import pandas as pd


def main():
    parser = argparse.ArgumentParser(description="游资席位胜率分析")
    parser.add_argument("--top",         type=int, default=30,   help="显示Top N席位")
    parser.add_argument("--min-records", type=int, default=30,   help="最少上榜次数")
    parser.add_argument("--output",      default="analysis/seat_ranking.csv")
    args = parser.parse_args()

    # ── 计算 ──────────────────────────────────────────────────────
    df = calc_seat_winrate(min_records=args.min_records)
    if df.empty:
        logger.error("无数据，退出")
        return

    # ── 保存完整排名 ──────────────────────────────────────────────
    os.makedirs("analysis", exist_ok=True)
    df.to_csv(args.output, encoding="utf-8-sig")
    logger.success(f"完整排名已保存: {args.output}（{len(df)} 席位）")

    # ── 高质量席位筛选 ────────────────────────────────────────────
    hq = filter_high_quality(df)

    # ── 打印 ──────────────────────────────────────────────────────
    pd.set_option("display.max_colwidth", 38)
    pd.set_option("display.float_format", lambda x: f"{x:.2f}")
    pd.set_option("display.width", 120)

    cols = ["seat_name", "total", "cnt_2024",
            "win_rate_1d", "avg_ret_1d",
            "win_rate_5d", "avg_ret_5d",
            "score"]

    print(f"\n{'='*110}")
    print(f"  游资席位排行榜  Top {min(args.top, len(df))}（按综合评分，min_records={args.min_records}）")
    print(f"{'='*110}")
    print(df[cols].head(args.top).to_string())

    print(f"\n{'='*110}")
    print(f"  高质量席位（5日胜率≥55% & 5日均收≥1.5%）  共 {len(hq)} 个")
    print(f"{'='*110}")
    if not hq.empty:
        print(hq[cols].head(args.top).to_string())
    else:
        print("  暂无满足条件的席位")

    print(f"\n总计: {len(df)} 个有效席位（出现≥{args.min_records}次）")
    print(f"拉萨系席位: {len(df[df['seat_name'].str.contains('拉萨', na=False)])} 个\n")


if __name__ == "__main__":
    main()
