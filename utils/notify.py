"""
推送工具 — 双通道：ntfy.sh（主） + Server Chan（备）

ntfy.sh: 免费、无需注册、香港服务器可访问
  订阅方法: 下载 ntfy app → 订阅 topic "whale_tracker_chen"
  或浏览器: https://ntfy.sh/whale_tracker_chen

Server Chan: 国内方糖推送（HK服务器可能超时，作为备用）
"""

import requests
from loguru import logger
from config import SCT_KEY

# ntfy.sh topic（唯一即可，手机 app 订阅同名 topic）
NTFY_TOPIC = "whale_tracker_chen"
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"

# Server Chan 端点：优先用国际版（HK 可达），再试标准版
SCT_URLS = [
    f"https://sc.ftqq.com/{SCT_KEY}.send",       # 国际版
    f"https://sctapi.ftqq.com/{SCT_KEY}.send",    # 标准版
]


def push(title: str, body: str = "") -> bool:
    """
    推送消息到手机。
    优先 Server Chan 国际版，失败则 ntfy.sh 兜底。
    返回: True=至少一个通道成功
    """
    ok = _push_sct(title, body)
    if not ok:
        ok = _push_ntfy(title, body)
    return ok


def _push_ntfy(title: str, body: str = "") -> bool:
    """ntfy.sh 推送（香港可达）"""
    try:
        resp = requests.post(
            NTFY_URL,
            data=body.encode("utf-8") if body else title.encode("utf-8"),
            headers={
                "Title":    title[:255].encode("utf-8"),
                "Priority": "default",
                "Tags":     "whale",
            },
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info(f"📱 ntfy 推送成功: {title[:30]}")
            return True
        logger.warning(f"ntfy 推送失败: {resp.status_code}")
        return False
    except Exception as e:
        logger.warning(f"ntfy 异常: {e}")
        return False


def _push_sct(title: str, body: str = "") -> bool:
    """Server Chan 推送（依次尝试国际版 → 标准版）"""
    for url in SCT_URLS:
        try:
            resp = requests.post(
                url,
                data={"title": title[:64], "desp": body},
                timeout=8,
            )
            data = resp.json()
            if data.get("data", {}).get("errno") == 0 or data.get("code") == 0:
                logger.info(f"📱 SCT 推送成功: {title[:30]}  ({url.split('/')[2]})")
                return True
            logger.debug(f"SCT 端点 {url.split('/')[2]} 返回: {data}")
        except Exception as e:
            logger.debug(f"SCT 端点 {url.split('/')[2]} 超时: {e}")
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
