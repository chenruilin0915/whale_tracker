#!/bin/bash
# ============================================================
# whale_tracker 服务器一键安装脚本
# 在腾讯云网页终端粘贴运行：
#   curl -sSL https://raw.githubusercontent.com/chenruilin0915/whale_tracker/main/server_setup.sh | bash
# ============================================================

set -e
G="\033[0;32m"; Y="\033[1;33m"; N="\033[0m"
ok()   { echo -e "${G}[✓]${N} $1"; }
warn() { echo -e "${Y}[!]${N} $1"; }

echo ""
echo "================================================"
echo "  whale_tracker 服务器安装"
echo "================================================"
echo ""

# Step 1：安装系统依赖
echo "Step 1：安装依赖..."
apt-get update -q && apt-get install -y -q python3-pip screen git
ok "系统依赖安装完成"

# Step 2：克隆代码
echo ""
echo "Step 2：拉取代码..."
if [ -d "$HOME/whale_tracker" ]; then
    warn "目录已存在，更新代码..."
    cd ~/whale_tracker && git pull
else
    git clone https://github.com/chenruilin0915/whale_tracker.git ~/whale_tracker
fi
ok "代码拉取完成"

# Step 3：安装 Python 依赖
echo ""
echo "Step 3：安装 Python 依赖..."
cd ~/whale_tracker
pip3 install -r requirements.txt -q
ok "Python 依赖安装完成"

# Step 4：创建目录
mkdir -p ~/whale_tracker/{data,logs,analysis}

# Step 5：初始化数据库
echo ""
echo "Step 4：初始化数据库..."
python3 scripts/init_db.py
ok "数据库初始化完成"

# Step 6：后台启动采集（龙虎榜列表 + 席位明细 + K线）
echo ""
echo "Step 5：后台启动全量数据采集..."
screen -dmS whale_fetch bash -c '
    cd ~/whale_tracker
    echo "[$(date)] 开始采集龙虎榜列表..." >> logs/fetch.log
    python3 scripts/fetch_history.py --step lhb >> logs/fetch.log 2>&1
    echo "[$(date)] 龙虎榜完成，开始采集席位明细..." >> logs/fetch.log
    python3 scripts/fetch_history.py --step seats >> logs/fetch.log 2>&1
    echo "[$(date)] 席位明细完成，开始采集K线..." >> logs/fetch.log
    python3 scripts/fetch_history.py --step kline >> logs/fetch.log 2>&1
    echo "[$(date)] 全部完成！" >> logs/fetch.log
'
ok "采集任务已在后台启动（screen 会话：whale_fetch）"

# 等2秒看日志头部
sleep 2
echo ""
echo "--- 当前日志 ---"
tail -5 ~/whale_tracker/logs/fetch.log 2>/dev/null || echo "（日志生成中...）"

echo ""
echo "================================================"
echo -e "${G}  安装完成！${N}"
echo "================================================"
echo ""
echo "  查看采集进度："
echo "    cd ~/whale_tracker && python3 scripts/check_db.py"
echo ""
echo "  查看实时日志："
echo "    tail -f ~/whale_tracker/logs/fetch.log"
echo ""
echo "  进入采集会话（Ctrl+A D 退出不中断）："
echo "    screen -r whale_fetch"
echo ""
