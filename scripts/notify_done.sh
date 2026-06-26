#!/bin/bash
# ============================================================
# 采集完成后推送微信通知（Server酱）
# 用法：bash scripts/notify_done.sh &
# ============================================================

SEND_KEY="SCT308342TFje2T0AxdJDaE1HjkxNYcrhf"
LOG_FILE="$HOME/whale_tracker/logs/fetch.log"
CHECK_DB="cd $HOME/whale_tracker && python3 scripts/check_db.py"

send_wechat() {
    local title="$1"
    local content="$2"
    curl -s "https://sctapi.ftqq.com/${SEND_KEY}.send" \
        --data-urlencode "title=${title}" \
        --data-urlencode "desp=${content}" \
        -o /dev/null
}

echo "[$(date)] 监控启动，等待采集完成..."

# ── 每4小时发一次进度通知 ─────────────────────────────────
progress_notify() {
    local lhb=$(grep -c "lhb_daily" $HOME/whale_tracker/data/whale.db 2>/dev/null || \
        sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM lhb_daily;" 2>/dev/null || echo "?")
    local seats=$(sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM lhb_seat_detail;" 2>/dev/null || echo "?")
    local kline=$(sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM stock_daily;" 2>/dev/null || echo "?")
    local done_tasks=$(sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM fetch_log WHERE status='done';" 2>/dev/null || echo "?")
    local total_tasks=151930  # 75435 * 2 + 1

    send_wechat "🐋 whale_tracker 采集进度" \
"**采集进度报告**

- 龙虎榜列表：${lhb} 条
- 席位明细：${seats} 条
- 日K线：${kline} 条
- 完成任务：${done_tasks} 个

时间：$(date '+%Y-%m-%d %H:%M')"
}

LAST_PROGRESS=$(date +%s)

# ── 主循环 ────────────────────────────────────────────────
while true; do
    sleep 60

    # 检查是否全部完成
    if grep -q "全部采集完成" "$LOG_FILE" 2>/dev/null; then
        SEATS=$(sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM lhb_seat_detail;" 2>/dev/null || echo "?")
        KLINE=$(sqlite3 $HOME/whale_tracker/data/whale.db "SELECT COUNT(*) FROM stock_daily;" 2>/dev/null || echo "?")

        send_wechat "✅ whale_tracker 全部采集完成！" \
"**数据采集完成**

- 席位明细：${SEATS} 条
- 日K线：${KLINE} 条

可以开始 Week 2 席位胜率分析了 🎉

完成时间：$(date '+%Y-%m-%d %H:%M')"

        echo "[$(date)] 完成通知已发送"
        exit 0
    fi

    # 检查采集进程是否意外退出
    if ! screen -list | grep -q "whale_fetch"; then
        # 进程不在了但没有完成标记，可能是出错了
        LAST_LOG=$(tail -3 "$LOG_FILE" 2>/dev/null)
        send_wechat "⚠️ whale_tracker 采集进程异常退出" \
"**进程已停止，请检查**

最后日志：
${LAST_LOG}

时间：$(date '+%Y-%m-%d %H:%M')"
        echo "[$(date)] 异常退出通知已发送"
        exit 1
    fi

    # 每4小时发一次进度
    NOW=$(date +%s)
    if (( NOW - LAST_PROGRESS >= 14400 )); then
        progress_notify
        LAST_PROGRESS=$NOW
        echo "[$(date)] 进度通知已发送"
    fi

done
