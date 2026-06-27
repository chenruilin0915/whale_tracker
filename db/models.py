"""
数据库模型定义（SQLAlchemy ORM）

表结构：
  lhb_daily       - 龙虎榜每日上榜记录（股票维度）
  lhb_seat_detail - 龙虎榜席位明细（买方/卖方）
  stock_daily     - 日K线行情
  fetch_log       - 采集进度日志（断点续传用）
"""

from sqlalchemy import (
    Column, Date, Float, Index, Integer,
    String, Text, UniqueConstraint, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────
# 1. 龙虎榜每日上榜记录
# ─────────────────────────────────────────────────────────────
class LhbDaily(Base):
    """
    每日龙虎榜——股票维度
    来源：ak.stock_lhb_detail_em()
    """
    __tablename__ = "lhb_daily"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    code         = Column(String(10), nullable=False, comment="股票代码")
    name         = Column(String(20), comment="股票名称")
    date         = Column(Date, nullable=False, comment="上榜日期")

    close_price  = Column(Float, comment="收盘价")
    change_rate  = Column(Float, comment="涨跌幅 %")

    # 龙虎榜资金（单位：元）
    net_buy_amt  = Column(Float, comment="龙虎榜净买额")
    buy_amt      = Column(Float, comment="龙虎榜买入额")
    sell_amt     = Column(Float, comment="龙虎榜卖出额")
    deal_amt     = Column(Float, comment="龙虎榜成交额")
    total_amt    = Column(Float, comment="市场总成交额")

    net_ratio    = Column(Float, comment="净买额/总成交 %")
    deal_ratio   = Column(Float, comment="成交额/总成交 %")
    turnover     = Column(Float, comment="换手率 %")
    free_cap     = Column(Float, comment="流通市值")

    reason       = Column(Text, comment="上榜原因")

    # akshare 已算好的后续收益率（%）
    d1_ret       = Column(Float, comment="上榜后1日涨跌幅")
    d2_ret       = Column(Float, comment="上榜后2日涨跌幅")
    d5_ret       = Column(Float, comment="上榜后5日涨跌幅")
    d10_ret      = Column(Float, comment="上榜后10日涨跌幅")

    __table_args__ = (
        UniqueConstraint("code", "date", name="uq_lhb_code_date"),
        Index("ix_lhb_date", "date"),
        Index("ix_lhb_code", "code"),
    )


# ─────────────────────────────────────────────────────────────
# 2. 龙虎榜席位明细
# ─────────────────────────────────────────────────────────────
class LhbSeatDetail(Base):
    """
    龙虎榜席位明细——买方或卖方各5席
    来源：ak.stock_lhb_stock_detail_em()
    """
    __tablename__ = "lhb_seat_detail"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    code          = Column(String(10), nullable=False, comment="股票代码")
    date          = Column(Date, nullable=False, comment="上榜日期")
    direction     = Column(String(4), nullable=False, comment="方向：买入/卖出")

    seat_name     = Column(String(100), comment="交易营业部名称")
    seat_type     = Column(String(20), comment="席位类型：机构/游资/北向/未知")

    buy_amt       = Column(Float, comment="买入金额（元）")
    buy_ratio     = Column(Float, comment="买入额占总成交比 %")
    sell_amt      = Column(Float, comment="卖出金额（元）")
    sell_ratio    = Column(Float, comment="卖出额占总成交比 %")
    net_amt       = Column(Float, comment="净额（元）")

    __table_args__ = (
        Index("ix_seat_code_date", "code", "date"),
        Index("ix_seat_name", "seat_name"),
    )


# ─────────────────────────────────────────────────────────────
# 3. 日K线
# ─────────────────────────────────────────────────────────────
class StockDaily(Base):
    """
    日K线行情（前复权）
    来源：ak.stock_zh_a_hist(adjust="qfq")
    """
    __tablename__ = "stock_daily"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    code        = Column(String(10), nullable=False, comment="股票代码")
    date        = Column(Date, nullable=False, comment="交易日期")

    open        = Column(Float)
    close       = Column(Float)
    high        = Column(Float)
    low         = Column(Float)
    volume      = Column(Float, comment="成交量（手）")
    amount      = Column(Float, comment="成交额（元）")
    amplitude   = Column(Float, comment="振幅 %")
    change_rate = Column(Float, comment="涨跌幅 %")
    change_amt  = Column(Float, comment="涨跌额")
    turnover    = Column(Float, comment="换手率 %")

    __table_args__ = (
        UniqueConstraint("code", "date", name="uq_stock_code_date"),
        Index("ix_stock_date", "date"),
        Index("ix_stock_code", "code"),
    )


# ─────────────────────────────────────────────────────────────
# 4. 采集进度日志（断点续传）
# ─────────────────────────────────────────────────────────────
class FetchLog(Base):
    """
    记录每个采集任务的完成状态，避免重复请求。

    task_key 格式约定：
      lhb_list:YYYYMM          龙虎榜列表（按月）
      lhb_seat:CODE:YYYYMMDD   某股票某日席位明细
      kline:CODE               某股票全量K线
    """
    __tablename__ = "fetch_log"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    task_key   = Column(String(100), unique=True, nullable=False)
    status     = Column(String(10), default="done", comment="done/error")
    rows       = Column(Integer, default=0, comment="写入行数")
    error_msg  = Column(Text, comment="错误信息")
    fetched_at = Column(String(30), comment="完成时间 ISO8601")


# ─────────────────────────────────────────────────────────────
# 5. 模拟持仓记录
# ─────────────────────────────────────────────────────────────
class PaperPosition(Base):
    """
    模拟盘持仓记录
    status: pending（信号已生成，等待T+1开盘买入）
            open   （已买入，持仓中）
            closed （已平仓）
    """
    __tablename__ = "paper_positions"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    code         = Column(String(10), nullable=False)
    name         = Column(String(20))
    signal_date  = Column(Date, comment="信号日（龙虎榜日期）")
    entry_date   = Column(Date, comment="买入日期（T+1）")
    entry_price  = Column(Float, comment="买入价（开盘价）")
    shares       = Column(Integer, comment="股数（100股整倍）")
    cost         = Column(Float, comment="买入总金额（元）")
    status       = Column(String(10), default="pending")
    signal_seat  = Column(String(100), comment="触发席位")
    signal_score = Column(Float)
    exit_date    = Column(Date)
    exit_price   = Column(Float)
    exit_reason  = Column(String(20), comment="take_profit/stop_loss/max_hold/manual")
    pnl          = Column(Float, comment="盈亏（元）")
    pnl_pct      = Column(Float, comment="盈亏%")
    created_at   = Column(String(30))

    __table_args__ = (
        Index("ix_paper_status", "status"),
        Index("ix_paper_code", "code"),
    )


def init_db(db_url: str) -> None:
    """创建所有表（幂等）"""
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(engine)
    engine.dispose()
    print(f"[DB] 初始化完成 → {db_url}")
