#!/bin/bash
# 设置每日自动化 cron 任务
# 运行一次即可：bash scripts/setup_cron.sh

PROJ="/home/ubuntu/whale_tracker"
PYTHON="python3"
LOG="$PROJ/logs"

mkdir -p "$LOG"

# 导出当前 crontab，追加新任务，重新导入
(crontab -l 2>/dev/null; cat <<EOF

# ── Whale Tracker 自动化 ──────────────────────────────────────
# 早盘开仓：09:35（工作日）
35 9 * * 1-5 cd $PROJ && $PYTHON scripts/morning_open.py >> $LOG/morning.log 2>&1

# 收盘检查 + 新信号：15:35（工作日）
35 15 * * 1-5 cd $PROJ && $PYTHON scripts/evening_check.py >> $LOG/evening.log 2>&1

# 每周日更新席位评分缓存（拉最新数据）
0 10 * * 0 cd $PROJ && $PYTHON scripts/daily_update.py --days 7 >> $LOG/update.log 2>&1
EOF
) | crontab -

echo "✅ Cron 任务已设置:"
crontab -l | grep -A 10 "Whale Tracker"
