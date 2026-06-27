"""
Server Chan（方糖）推送工具

官网: https://sct.ftqq.com
发送接口: POST https://sctapi.ftqq.com/{key}.send
"""

import requests
from loguru import logger
from config import SCT_KEY

SCT_URL = f"https://sctapi.ftqq.com/{SCT_KEY}.send"


def push(title: str, body: str = "") -> bool:
    """
    推送消息到手机。
    title: 标题（最多64字符，必填）
    body:  正文（Markdown格式，可选）
    返回: True=成功, False=失败
    """
    try:
        resp = requests.post(
            SCT_URL,
            data={"title": title[:64], "desp": body},
            timeout=10,
        )
        data = resp.json()
        if data.get("data", {}).get("errno") == 0 or data.get("code") == 0:
            logger.info(f"📱 推送成功: {title[:30]}")
            return True
        else:
            logger.warning(f"推送失败: {data}")
            return False
    except Exception as e:
        logger.warning(f"推送异常: {e}")
        return False


def push_signals(signals, trade_date: str):
    """推送当日信号列表"""
    if signals.empty:
        push(f"🐋 {trade_date} 无信号", "今日龙虎榜无满足条件的游资席位出现。")
        return

    lines = [f"**共 {len(signals)} 个候选 | 每仓 20,000 元**\n"]
    for _, row in signals.iterrows():
        lines.append(
            f"**{row['code']} {row['name']}**  "
            f"今日 {row['today_gain']:+.1f}%\n"
            f"> 席位: {row['best_seat']}  \n"
            f"> 5日胜率: {row['win_rate_5d']:.0%}  均收: {row['avg_ret_5d']:.1f}%  评分: {row['score']:.2f}\n"
        )
    lines.append("\n⚠️ T+1开盘买入，止损-3%，目标+7%")

    push(f"🐋 游资信号 {trade_date} ({len(signals)}只)", "\n".join(lines))


def push_open(code: str, name: str, price: float, shares: int, cost: float):
    """推送开仓通知"""
    push(
        f"✅ 开仓 {code} {name}",
        f"**买入价**: {price:.2f} 元  \n"
        f"**股数**: {shares} 股  \n"
        f"**金额**: {cost:,.0f} 元  \n"
        f"止损: {price * 0.97:.2f} | 目标: {price * 1.07:.2f}"
    )


def push_close(code: str, name: str, entry: float, exit_price: float,
               pnl: float, pnl_pct: float, reason: str):
    """推送平仓通知"""
    emoji = "🟢" if pnl >= 0 else "🔴"
    reason_map = {
        "take_profit": "🎯 止盈",
        "stop_loss":   "🛑 止损",
        "max_hold":    "⏰ 到期",
        "manual":      "✋ 手动",
    }
    label = reason_map.get(reason, reason)
    push(
        f"{emoji} 平仓 {code} {name}  {pnl_pct:+.1f}%",
        f"**{label}**  \n"
        f"买入: {entry:.2f} → 卖出: {exit_price:.2f}  \n"
        f"盈亏: **{pnl:+,.0f} 元** ({pnl_pct:+.2f}%)"
    )


def push_daily_summary(date_str: str, open_pos: list, closed_today: list, total_pnl: float):
    """推送每日收盘汇总"""
    lines = [f"**日期**: {date_str}\n"]

    if closed_today:
        lines.append("### 今日平仓")
        for p in closed_today:
            emoji = "🟢" if p["pnl"] >= 0 else "🔴"
            lines.append(
                f"{emoji} {p['code']} {p['name']}  "
                f"{p['pnl_pct']:+.1f}% ({p['pnl']:+,.0f}元)  [{p['exit_reason']}]"
            )

    if open_pos:
        lines.append("\n### 持仓中")
        for p in open_pos:
            hold_days = p.get("hold_days", "?")
            pnl_str = f"{p['float_pct']:+.1f}%" if "float_pct" in p else ""
            lines.append(f"📌 {p['code']} {p['name']}  持{hold_days}天  {pnl_str}")

    lines.append(f"\n**今日盈亏**: {'🟢' if total_pnl >= 0 else '🔴'} **{total_pnl:+,.0f} 元**")

    push(
        f"🐋 每日汇总 {date_str}  {total_pnl:+,.0f}元",
        "\n".join(lines)
    )
