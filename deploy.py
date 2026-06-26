#!/usr/bin/env python3
"""
whale_tracker 一键部署脚本（Python版，无需 sshpass）
用法：在本地 whale_tracker 目录下运行：
  python3 deploy.py
"""

import os
import sys
import stat
import tarfile
import tempfile
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────
SERVER   = "43.129.181.228"
PORT     = 22
USER     = "root"
PASSWORD = "Raining820915!"
REMOTE   = "/root/whale_tracker"
LOCAL    = Path(__file__).parent

# ── 颜色 ──────────────────────────────────────────────────
G = "\033[0;32m"; Y = "\033[1;33m"; R = "\033[0;31m"; N = "\033[0m"
def ok(msg):   print(f"{G}[✓]{N} {msg}")
def warn(msg): print(f"{Y}[!]{N} {msg}")
def err(msg):  print(f"{R}[✗]{N} {msg}"); sys.exit(1)
def step(n, msg): print(f"\nStep {n}：{msg}...")


# ── 安装 paramiko ─────────────────────────────────────────
try:
    import paramiko
except ImportError:
    print("安装 paramiko...")
    os.system(f"{sys.executable} -m pip install paramiko -q")
    import paramiko

try:
    from scp import SCPClient
except ImportError:
    os.system(f"{sys.executable} -m pip install scp -q")
    from scp import SCPClient


# ── SSH 连接 ──────────────────────────────────────────────
def connect():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(SERVER, port=PORT, username=USER, password=PASSWORD, timeout=20)
    return client


def run(client, cmd, show=True):
    """执行命令，返回输出"""
    _, stdout, stderr = client.exec_command(cmd, timeout=120)
    out = stdout.read().decode().strip()
    er  = stderr.read().decode().strip()
    if show and out: print(f"    {out}")
    if show and er:  print(f"    {Y}{er}{N}")
    return out, er


# ── 主流程 ────────────────────────────────────────────────
def main():
    print(f"""
{'='*54}
  whale_tracker 自动部署
  目标服务器：{USER}@{SERVER}
{'='*54}""")

    # Step 1：连接
    step(1, "连接服务器")
    try:
        ssh = connect()
        ok("SSH 连接成功")
    except Exception as e:
        err(f"连接失败：{e}")

    # Step 2：检查环境
    step(2, "检查服务器环境")
    out, _ = run(ssh, "python3 --version 2>&1")
    ok(f"Python：{out}")
    out, _ = run(ssh, "lsb_release -d 2>/dev/null | cut -d: -f2 | xargs || grep PRETTY /etc/os-release | cut -d= -f2 | tr -d '\"'")
    ok(f"系统：{out}")

    # Step 3：创建目录结构
    step(3, "创建服务器目录")
    run(ssh, f"mkdir -p {REMOTE}/{{data,db,fetchers,scripts,analysis,logs}}", show=False)
    ok("目录结构创建完成")

    # Step 4：打包并上传项目文件
    step(4, "上传项目文件")
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name

    # 打包（排除 data 目录和 __pycache__）
    with tarfile.open(tmp_path, "w:gz") as tar:
        for item in LOCAL.iterdir():
            if item.name in ("data", "__pycache__", ".DS_Store", "deploy.py", "deploy.sh"):
                continue
            tar.add(item, arcname=item.name)

    size = os.path.getsize(tmp_path) / 1024
    print(f"    打包完成（{size:.1f} KB），正在上传...")

    with SCPClient(ssh.get_transport()) as scp:
        scp.put(tmp_path, f"/tmp/whale_code.tar.gz")

    run(ssh, f"cd {REMOTE} && tar xzf /tmp/whale_code.tar.gz && rm /tmp/whale_code.tar.gz", show=False)
    os.unlink(tmp_path)
    ok("代码上传完成")

    # Step 5：迁移本地数据库
    step(5, "迁移本地数据库（龙虎榜75,435条）")
    db_path = LOCAL / "data" / "whale.db"
    if db_path.exists():
        size_mb = db_path.stat().st_size / 1024 / 1024
        print(f"    发现 whale.db（{size_mb:.1f} MB），正在上传...")
        with SCPClient(ssh.get_transport()) as scp:
            scp.put(str(db_path), f"{REMOTE}/data/whale.db")
        ok("数据库迁移完成（省去重新采集龙虎榜列表）")
    else:
        warn("本地未找到 whale.db，将在服务器重新初始化")

    # Step 6：安装依赖
    step(6, "安装 Python 依赖")
    print("    （首次安装约1~2分钟）")
    out, er = run(ssh, f"cd {REMOTE} && pip3 install -r requirements.txt -q 2>&1 | tail -5")
    ok("依赖安装完成")

    # Step 7：初始化数据库
    step(7, "初始化数据库表结构")
    run(ssh, f"cd {REMOTE} && python3 scripts/init_db.py")
    ok("数据库初始化完成")

    # Step 8：验证数据
    step(8, "验证数据库状态")
    run(ssh, f"cd {REMOTE} && python3 scripts/check_db.py")

    # Step 9：后台启动席位明细采集
    step(9, "后台启动席位明细采集")
    # 先检查是否已有在跑的任务
    out, _ = run(ssh, "pgrep -f 'fetch_history' | wc -l", show=False)
    if int(out.strip()) > 0:
        warn("检测到已有采集任务在运行，跳过重复启动")
    else:
        # 用 nohup 后台运行，日志写入 logs/seats.log
        run(ssh,
            f"cd {REMOTE} && nohup python3 scripts/fetch_history.py --step seats "
            f"> logs/seats.log 2>&1 &",
            show=False)
        import time; time.sleep(2)
        # 确认进程存在
        out, _ = run(ssh, "pgrep -f 'fetch_history' | wc -l", show=False)
        if int(out.strip()) > 0:
            ok("采集任务已在后台启动 ✓")
            # 看前几行日志确认正常
            run(ssh, f"sleep 2 && tail -5 {REMOTE}/logs/seats.log")
        else:
            warn("进程未检测到，请手动检查")

    # ── 完成提示 ─────────────────────────────────────────
    print(f"""
{'='*54}
{G}  部署完成！{N}
{'='*54}

  查看采集进度：
    ssh {USER}@{SERVER}
    cd ~/whale_tracker && python3 scripts/check_db.py

  查看实时日志：
    tail -f ~/whale_tracker/logs/seats.log

  席位明细预计 30~40 小时，可随时中断续传：
    python3 scripts/fetch_history.py --step seats

  席位完成后跑 K 线：
    python3 scripts/fetch_history.py --step kline
""")
    ssh.close()


if __name__ == "__main__":
    main()
