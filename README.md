# Alt-data radar V1

## 1. 准备
- 企业微信群 -> 添加群机器人 -> 复制 Webhook 地址
- 编辑 monitor_pool.csv（先 15-20 个品牌；回测前固定，别事后挑）

## 2. 云端运行（Trends 雷达）
1. 新建 **私有** GitHub 仓库，上传本目录全部文件
2. Settings -> Secrets and variables -> Actions -> New secret：名称 WECOM_WEBHOOK，值为 Webhook 地址
3. Actions 页面手动 Run workflow 一次测试；之后每天北京时间 8:00 自动跑
4. 若 Google 限流频繁（收到"运行异常"推送），改为本地定时运行 radar.py

## 3. 本地运行
- pip install -r requirements.txt
- python radar.py            # 先 set WECOM_WEBHOOK=...，不设置则只打印
- python snapshot.py         # 亚马逊快照，先在 asins.csv 填真实 ASIN；每天一次
- python backtest.py         # 历史回测，结果在 data/backtest_events.csv
