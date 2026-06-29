"""
Week 3: 每日信号过滤器

每日收盘后（15:30后）运行，从当日龙虎榜中筛选高胜率游资席位出现的股票，
输出次日 T+1 跟单候选列表。

核心逻辑：
  1. 获取当日龙虎榜列表（股票维度）
  2. 获取每只股票的买入席位
  3. 比对 seat_ranking，过滤高质量席位
  4. 排除拉萨系、今日已大涨等噪音
  5. 输出信号，含建议仓位
"""

import time
from datetime import date, datetime
from typing import Optional

import akshare as ak
import pandas as pd
from loguru import logger

from analysis.seat_winrate import calc_seat_winrate

# ── 信号过滤参数 ──────────────────────────────────────────────────
MIN_SEAT_WIN_RATE  = 0.60   # 席位5日胜率门槛
MIN_SEAT_SCORE     = 0.70   # 席位综合评分门槛
MIN_SEAT_RECORDS   = 30     # 席位历史最少出现次数
MAX_TODAY_GAIN     = 7.0    # 今日涨幅上限（%）：避免追高
MAX_TODAY_DROP     = -5.0   # 今日跌幅下限（%）：避免接刀
MAX_STOCK_PRICE    = 150.0  # 股价上限（元）：低价股更容易拉升

# 排除席位关键词（基于Week 2分析：拉萨系是T+0游资，T+1跟单负收益）
EXCLUDE_SEAT_KEYWORDS = ["拉萨", "申港"]

# 建议仓位（总资金10万）
TOTAL_CAPITAL  = 100_000
MAX_POSITIONS  = 5
POSITION_SIZE  = TOTAL_CAPITAL // MAX_POSITIONS  # 每只2万


def _load_seat_ranking(min_records: int = MIN_SEAT_RECORDS) -> pd.DataFrame:
    """加载席位评分表（优先从CSV缓存，否则实时计算）"""
    import os
    csv_path = "analysis/seat_ranking.csv"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, index_col=0)
        logger.info(f"席位评分表已从缓存加载: {len(df)} 个席位")
    else:
        logger.info("未找到缓存，重新计算席位评分...")
        df = calc_seat_winrate(min_records=min_records)
        os.makedirs("analysis", exist_ok=True)
        df.to_csv(csv_path, encoding="utf-8-sig")
    return df


def _is_excluded_seat(seat_name: str) -> bool:
    """判断是否为排除席位（拉萨系等T+0游资）"""
    return any(kw in seat_name for kw in EXCLUDE_SEAT_KEYWORDS)


def fetch_today_lhb(trade_date: str) -> Optional[pd.DataFrame]:
    """
    获取指定日期的龙虎榜列表。
    trade_date: YYYYMMDD
    """
    try:
        df = ak.stock_lhb_detail_em(start_date=trade_date, end_date=trade_date)
        if df is None or df.empty:
            logger.warning(f"{trade_date} 无龙虎榜数据（可能非交易日）")
            return None
        logger.info(f"{trade_date} 龙虎榜共 {len(df)} 只股票上榜")
        return df
    except Exception as e:
        logger.error(f"获取龙虎榜失败: {e}")
        return None


def fetch_seat_detail(code: str, trade_date: str) -> list:
    """获取单只股票的买入席位名称列表"""
    try:
        df = ak.stock_lhb_stock_detail_em(symbol=code, date=trade_date, flag="买入")
        if df is None or df.empty:
            return []
        return df["交易营业部名称"].dropna().tolist()
    except Exception as e:
        logger.debug(f"  {code} 席位获取失败: {e}")
        return []


def generate_signals(
    trade_date: Optional[str] = None,
    seat_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    主函数：生成当日 T+1 信号列表。

    Parameters
    ----------
    trade_date : YYYYMMDD，默认今日
    seat_df    : 席位评分表，None 则自动加载

    Returns
    -------
    DataFrame，列：code/name/best_seat/win_rate_5d/avg_ret_5d/score/
                   today_gain/close_price/reason/position_size
    """
    if trade_date is None:
        trade_date = datetime.now().strftime("%Y%m%d")

    logger.info(f"{'='*60}")
    logger.info(f"信号生成  日期: {trade_date}")
    logger.info(f"{'='*60}")

    # ── Step 1: 加载席位评分 ─────────────────────────────────────
    if seat_df is None:
        seat_df = _load_seat_ranking()

    # 构建席位名称 → 评分行 的快速查询字典
    seat_map = seat_df.set_index("seat_name").to_dict("index")

    # ── Step 2: 获取当日龙虎榜 ───────────────────────────────────
    lhb_df = fetch_today_lhb(trade_date)
    if lhb_df is None:
        return pd.DataFrame()

    signals = []

    for _, row in lhb_df.iterrows():
        code        = str(row["代码"]).zfill(6)
        name        = row.get("名称", "")
        change_rate = float(row.get("涨跌幅", 0) or 0)
        close_price = float(row.get("收盘价", 0) or 0)
        reason      = row.get("上榜原因", "")

        # ── 股票基础过滤 ─────────────────────────────────────────
        if change_rate > MAX_TODAY_GAIN:
            logger.debug(f"  {code} {name} 跳过：今日涨幅 {change_rate:.1f}% 过高")
            continue
        if change_rate < MAX_TODAY_DROP:
            logger.debug(f"  {code} {name} 跳过：今日跌幅 {change_rate:.1f}% 过深")
            continue
        if 0 < close_price > MAX_STOCK_PRICE:
            logger.debug(f"  {code} {name} 跳过：股价 {close_price:.2f} 过高")
            continue

        # ── 获取买入席位 ─────────────────────────────────────────
        time.sleep(0.5)
        buying_seats = fetch_seat_detail(code, trade_date)
        if not buying_seats:
            continue

        # ── 席位质量评估 ─────────────────────────────────────────
        best_seat  = None
        best_score = 0.0

        for seat_name in buying_seats:
            if _is_excluded_seat(seat_name):
                continue
            if seat_name not in seat_map:
                continue

            info = seat_map[seat_name]
            if info["win_rate_5d"] < MIN_SEAT_WIN_RATE:
                continue
            if info["score"] < MIN_SEAT_SCORE:
                continue
            if info["total"] < MIN_SEAT_RECORDS:
                continue

            if info["score"] > best_score:
                best_score = info["score"]
                best_seat  = seat_name

        if best_seat is None:
            continue

        info = seat_map[best_seat]
        signals.append({
            "code":         code,
            "name":         name,
            "best_seat":    best_seat,
            "win_rate_1d":  round(info["win_rate_1d"], 3),
            "avg_ret_1d":   round(info["avg_ret_1d"],  2),
            "win_rate_5d":  round(info["win_rate_5d"], 3),
            "avg_ret_5d":   round(info["avg_ret_5d"],  2),
            "seat_total":   int(info["total"]),
            "score":        round(info["score"], 3),
            "today_gain":   round(change_rate, 2),
            "close_price":  close_price,
            "reason":       reason,
            "position_size": POSITION_SIZE,
        })
        logger.success(
            f"  ✓ 信号: {code} {name}  "
            f"席位: {best_seat[:15]}  "
            f"5日胜率: {info['win_rate_5d']:.0%}  "
            f"评分: {info['score']:.2f}"
        )

    if not signals:
        logger.info("今日无满足条件的信号")
        return pd.DataFrame()

    result = pd.DataFrame(signals).sort_values("score", ascending=False)
    logger.success(f"信号生成完成: 共 {len(result)} 个 T+1 候选股票")
    return result


def format_signal_report(signals: pd.DataFrame, trade_date: str) -> str:
    """格式化信号报告（用于终端输出或推送）"""
    if signals.empty:
        return f"[{trade_date}] 今日无信号"

    lines = [
        f"",
        f"{'='*65}",
        f"  🐋 Whale Tracker 信号  {trade_date}",
        f"  共 {len(signals)} 个候选 | 每仓 {POSITION_SIZE:,} 元",
        f"{'='*65}",
    ]

    for i, row in signals.iterrows():
        lines.append(
            f"  {row['code']} {row['name'][:8]:<8}  "
            f"今日: {row['today_gain']:+.1f}%  "
            f"席位: {row['best_seat'][:16]}  "
            f"5日胜: {row['win_rate_5d']:.0%}  均收: {row['avg_ret_5d']:.1f}%"
        )

    lines += [
        f"{'='*65}",
        f"  ⚠ T+1开盘买入，止损-3%，目标+5%~+8%",
        f"{'='*65}",
    ]
    return "\n".join(lines)
