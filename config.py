"""
全局配置
"""
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
BASE_DIR = Path(__file__).parent

# SQLite 数据库放在项目目录下的 data/ 文件夹
# 注意：如果项目在网络挂载盘（NFS/SMB），SQLite 可能无法创建 journal 文件
# 此时可将 DB_PATH 改为本地路径，例如：
#   DB_PATH = Path.home() / "whale_tracker_data" / "whale.db"
DB_PATH = BASE_DIR / "data" / "whale.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

DB_URL = f"sqlite:///{DB_PATH}"

# ── 数据范围 ──────────────────────────────────────────
# 历史数据起止（5年）
HISTORY_START = "20200101"
HISTORY_END   = "20241231"

# ── 采集限速 ──────────────────────────────────────────
# 龙虎榜列表：按月批量请求，延迟较低
LHB_LIST_SLEEP   = 1.0   # 秒，每批次间隔

# 席位明细：每只股票×每日×买卖两次，请求量大，需要保守限速
LHB_DETAIL_SLEEP = 0.8   # 秒，每个线程的请求间隔

# 席位明细并发线程数（每个线程独立限速，总速度 = 线程数 × 1/SLEEP）
LHB_SEAT_WORKERS = 3

# K线：每只股票一次请求即拿全量历史，较快
KLINE_SLEEP      = 0.5   # 秒

# ── 游资席位过滤阈值（Week 2 使用） ───────────────────
SEAT_MIN_RECORDS   = 30    # 近5年至少出现30次才纳入评分
SEAT_MIN_WIN_RATE  = 0.55  # T+3 胜率下限
SEAT_MIN_AVG_RET   = 0.015 # T+3 平均收益下限（1.5%）

# ── 模拟盘参数（Week 4） ──────────────────────────────
PAPER_CAPITAL      = 100_000  # 总资金（元）
PAPER_MAX_POS      = 5        # 最多同时持仓数
PAPER_STOP_LOSS    = -0.03    # 止损线 -3%
PAPER_TAKE_PROFIT  = 0.07     # 止盈线 +7%
PAPER_MAX_HOLD     = 3        # 最大持仓天数

# ── Server Chan 推送（方糖） ──────────────────────────
SCT_KEY = "SCT308342TFje2T0AxdJDaE1HjkxNYcrhf"
