"""
Week 2: 席位胜率计算引擎

对每个游资席位统计近5年龙虎榜表现：
  - 上榜次数（买入方向）
  - T+1 / T+2 / T+5 胜率（涨跌幅 > 0 的比例）
  - T+1 / T+2 / T+5 平均收益（%）
  - 综合评分
"""

import pandas as pd
from sqlalchemy import text
from loguru import logger

from db.connection import get_engine
from config import SEAT_MIN_RECORDS, SEAT_MIN_WIN_RATE, SEAT_MIN_AVG_RET

# ── 查询 SQL ──────────────────────────────────────────────────────
# d1_ret / d2_ret / d5_ret / d10_ret 单位：% （如 3.25 = 3.25%）
# 只取买入方向游资席位，且 d5_ret 有值（排除过期/缺数据记录）
ANALYSIS_SQL = """
SELECT
    s.seat_name,
    COUNT(*)                                                                AS total,

    ROUND(AVG(CASE WHEN d.d1_ret  > 0 THEN 1.0 ELSE 0.0 END), 4)         AS win_rate_1d,
    ROUND(AVG(d.d1_ret),  2)                                               AS avg_ret_1d,

    ROUND(AVG(CASE WHEN d.d2_ret  > 0 THEN 1.0 ELSE 0.0 END), 4)         AS win_rate_2d,
    ROUND(AVG(d.d2_ret),  2)                                               AS avg_ret_2d,

    ROUND(AVG(CASE WHEN d.d5_ret  > 0 THEN 1.0 ELSE 0.0 END), 4)         AS win_rate_5d,
    ROUND(AVG(d.d5_ret),  2)                                               AS avg_ret_5d,

    ROUND(AVG(CASE WHEN d.d10_ret > 0 THEN 1.0 ELSE 0.0 END), 4)         AS win_rate_10d,
    ROUND(AVG(d.d10_ret), 2)                                               AS avg_ret_10d,

    -- 近12个月活跃度（2024年出现次数）
    SUM(CASE WHEN d.date >= '2024-01-01' THEN 1 ELSE 0 END)               AS cnt_2024

FROM lhb_seat_detail  s
JOIN lhb_daily        d  ON s.code = d.code AND s.date = d.date
WHERE s.seat_type  = '游资'
  AND s.direction  = '买入'
  AND d.d5_ret     IS NOT NULL
GROUP BY s.seat_name
HAVING COUNT(*) >= :min_records
ORDER BY win_rate_5d DESC, avg_ret_5d DESC
"""


def calc_seat_winrate(min_records: int = None) -> pd.DataFrame:
    """
    计算所有游资席位的胜率统计。
    返回 DataFrame，列：seat_name / total / win_rate_Xd / avg_ret_Xd / score
    """
    if min_records is None:
        min_records = SEAT_MIN_RECORDS

    engine = get_engine()
    logger.info(f"开始计算席位胜率（最少出现次数: {min_records}）...")

    with engine.connect() as conn:
        df = pd.read_sql(text(ANALYSIS_SQL), conn, params={"min_records": min_records})

    if df.empty:
        logger.warning("没有满足条件的席位，请检查数据或降低 min_records")
        return df

    logger.info(f"原始结果: {len(df)} 个席位")

    # ── 综合评分（0-1）────────────────────────────────────────────
    # 权重：5日胜率 50% + 5日均收（归一化） 30% + 1日胜率 20%
    max_ret = df["avg_ret_5d"].clip(-20, 20)
    df["score"] = (
        df["win_rate_5d"] * 0.5
        + (max_ret + 20) / 40 * 0.3   # 归一化到 [0,1]
        + df["win_rate_1d"] * 0.2
    ).round(4)

    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df.index += 1  # 排名从 1 开始

    logger.success(f"席位胜率计算完成，共 {len(df)} 个席位")
    return df


def filter_high_quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    按阈值过滤高质量席位：
      win_rate_5d >= SEAT_MIN_WIN_RATE
      avg_ret_5d  >= SEAT_MIN_AVG_RET（单位 %）
    """
    # config 里 SEAT_MIN_AVG_RET = 0.015 是小数，统一转成 %
    min_avg_ret_pct = SEAT_MIN_AVG_RET * 100 if SEAT_MIN_AVG_RET < 1 else SEAT_MIN_AVG_RET

    mask = (
        (df["win_rate_5d"] >= SEAT_MIN_WIN_RATE) &
        (df["avg_ret_5d"]  >= min_avg_ret_pct)
    )
    result = df[mask].copy()
    logger.info(
        f"高质量席位: {len(result)} 个"
        f"（5日胜率≥{SEAT_MIN_WIN_RATE*100:.0f}%, 5日均收≥{min_avg_ret_pct:.1f}%）"
    )
    return result


def top_seats_for_signal(seat_names: list, df: pd.DataFrame = None) -> pd.DataFrame:
    """
    给定当日出现的席位名列表，返回其历史评分排名。
    供 Week 3 信号过滤器调用。
    """
    if df is None:
        df = calc_seat_winrate()
    return df[df["seat_name"].isin(seat_names)].copy()
