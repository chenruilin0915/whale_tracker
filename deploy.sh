#!/bin/bash
# ============================================================
# whale_tracker 一键部署脚本
# 用法：在本地 whale_tracker 目录下运行：
#   bash deploy.sh
# ============================================================

set -e

SERVER="43.129.181.228"
USER="root"
PASS="Raining820915!"
REMOTE_DIR="~/whale_tracker"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

# 颜色输出
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[✓]${NC} $1"; }
warning() { echo -e "${YELLOW}[!]${NC} $1"; }

# ── 检查本地依赖 ─────────────────────────────────────────
echo ""
echo "=============================================="
echo "  whale_tracker 自动部署"
echo "  目标服务器：$USER@$SERVER"
echo "=============================================="
echo ""

if ! command -v sshpass &>/dev/null; then
    warning "未找到 sshpass，尝试安装..."
    if command -v brew &>/dev/null; then
        brew install sshpass 2>/dev/null || {
            # macOS brew 可能没有 sshpass，用 expect 替代
            warning "brew 安装失败，改用 expect 方式"
            USE_EXPECT=1
        }
    elif command -v apt-get &>/dev/null; then
        sudo apt-get install -y sshpass
    fi
fi

# 封装 SSH / SCP 命令（兼容 sshpass 和 expect）
ssh_cmd() {
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no "$USER@$SERVER" "$@"
}
scp_cmd() {
    sshpass -p "$PASS" scp -o StrictHostKeyChecking=no -r "$@"
}

# ── Step 1：检查服务器连通性 ──────────────────────────────
echo "Step 1：检查服务器连通性..."
ssh_cmd "echo '连接成功'" && info "SSH 连接正常"

# ── Step 2：检查服务器 Python 版本 ───────────────────────
echo ""
echo "Step 2：检查服务器环境..."
PYTHON_VER=$(ssh_cmd "python3 --version 2>&1")
info "服务器 Python：$PYTHON_VER"

OS_INFO=$(ssh_cmd "lsb_release -d 2>/dev/null | cut -d: -f2 | xargs || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2 | tr -d '\"'")
info "操作系统：$OS_INFO"

# ── Step 3：上传项目文件 ──────────────────────────────────
echo ""
echo "Step 3：上传项目文件..."
# 先在服务器创建目录
ssh_cmd "mkdir -p ~/whale_tracker/data ~/whale_tracker/db ~/whale_tracker/fetchers ~/whale_tracker/scripts ~/whale_tracker/analysis"

# 上传各目录（排除本地 data 目录，数据库单独处理）
scp_cmd "$LOCAL_DIR/config.py"       "$USER@$SERVER:~/whale_tracker/"
scp_cmd "$LOCAL_DIR/requirements.txt" "$USER@$SERVER:~/whale_tracker/"
scp_cmd "$LOCAL_DIR/db/"             "$USER@$SERVER:~/whale_tracker/"
scp_cmd "$LOCAL_DIR/fetchers/"       "$USER@$SERVER:~/whale_tracker/"
scp_cmd "$LOCAL_DIR/scripts/"        "$USER@$SERVER:~/whale_tracker/"

info "项目文件上传完成"

# ── Step 4：迁移本地已有数据库（龙虎榜75,435条）────────────
echo ""
echo "Step 4：迁移本地数据库（节省重新采集时间）..."
if [ -f "$LOCAL_DIR/data/whale.db" ]; then
    DB_SIZE=$(du -sh "$LOCAL_DIR/data/whale.db" | cut -f1)
    info "发现本地 whale.db（$DB_SIZE），正在上传..."
    scp_cmd "$LOCAL_DIR/data/whale.db" "$USER@$SERVER:~/whale_tracker/data/"
    info "数据库迁移完成"
else
    warning "本地未找到 whale.db，将在服务器重新初始化"
fi

# ── Step 5：服务器安装依赖 ───────────────────────────────
echo ""
echo "Step 5：安装 Python 依赖..."
ssh_cmd "cd ~/whale_tracker && pip3 install -r requirements.txt -q 2>&1 | tail -3"
info "依赖安装完成"

# ── Step 6：初始化数据库表结构 ───────────────────────────
echo ""
echo "Step 6：初始化数据库..."
ssh_cmd "cd ~/whale_tracker && python3 scripts/init_db.py"

# ── Step 7：验证数据 ─────────────────────────────────────
echo ""
echo "Step 7：验证数据库状态..."
ssh_cmd "cd ~/whale_tracker && python3 scripts/check_db.py"

# ── Step 8：用 nohup 后台启动采集 ───────────────────────
echo ""
echo "Step 8：后台启动席位明细采集..."

# 优先用 screen，否则用 nohup
HAS_SCREEN=$(ssh_cmd "command -v screen && echo yes || echo no" 2>/dev/null)

if echo "$HAS_SCREEN" | grep -q "yes"; then
    ssh_cmd "cd ~/whale_tracker && screen -dmS whale_seats bash -c 'python3 scripts/fetch_history.py --step seats >> logs/seats.log 2>&1; echo 完成' && mkdir -p logs"
    info "已用 screen 后台启动（会话名：whale_seats）"
    echo ""
    echo "  查看实时日志：ssh $USER@$SERVER 后执行 screen -r whale_seats"
else
    ssh_cmd "mkdir -p ~/whale_tracker/logs && cd ~/whale_tracker && nohup python3 scripts/fetch_history.py --step seats > logs/seats.log 2>&1 &"
    info "已用 nohup 后台启动"
    echo ""
    echo "  查看实时日志：ssh $USER@$SERVER 后执行 tail -f ~/whale_tracker/logs/seats.log"
fi

# ── 完成 ─────────────────────────────────────────────────
echo ""
echo "=============================================="
echo -e "${GREEN}  部署完成！${NC}"
echo "=============================================="
echo ""
echo "  查看采集进度（随时）："
echo "  ssh $USER@$SERVER"
echo "  cd ~/whale_tracker && python3 scripts/check_db.py"
echo ""
echo "  席位明细预计需要 30~40 小时，可随时中断续传"
echo "  完成后继续运行 K 线采集："
echo "  python3 scripts/fetch_history.py --step kline"
echo ""
