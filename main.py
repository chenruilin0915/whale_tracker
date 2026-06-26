pip install -r requirements.txt
python scripts/fetch_history.py --step lhb     # 先跑龙虎榜列表（~5分钟）
python scripts/check_db.py                      # 看进度
python scripts/fetch_history.py --step seats   # 席位明细（较慢，可中断续传）
python scripts/fetch_history.py --step kline   # K线