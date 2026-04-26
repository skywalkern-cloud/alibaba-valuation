#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里巴巴每日数据采集cron脚本
每日08:00自动运行，写入data/history.json

功能:
- 获取港股实时股价
- 获取财务数据
- 更新历史记录
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime, date
from typing import Optional, Dict, Any
import warnings
warnings.filterwarnings('ignore')

WORK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(WORK_DIR))

HISTORY_FILE = WORK_DIR / 'data' / 'history.json'


# ========== Data Fetchers ==========

@st.cache_data(ttl=300)
def get_realtime_price() -> Optional[float]:
    """获取港股实时股价 (akshare)"""
    try:
        import akshare as ak
        df = ak.hk_stock_spot_em()
        row = df[df['代码'] == '09988']
        if not row.empty:
            price = float(row['最新价'].values[0])
            if price > 0:
                return price
    except Exception as e:
        print(f"  ⚠️ 股价获取失败: {e}")
    return None


@st.cache_data(ttl=3600)
def get_financial_data() -> Dict[str, Any]:
    """获取财务数据 (EastMoney API)"""
    try:
        import requests
        url = 'https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/ZYZBAjaxNew?type=0&code=HK09988'
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data
    except Exception as e:
        print(f"  ⚠️ 财务数据获取失败: {e}")
    return {}


def get_snowball_data() -> Dict[str, Any]:
    """获取雪球热度数据"""
    try:
        import requests
        url = 'https://stock.xueqiu.com/v5/stock/recommend/get.json?symbol=HK09988&count=5&type=ALL'
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Cookie': 'xq_a_token=placeholder'  # 需要真实token
        }
        # 降级
    except:
        pass
    return {}


# ========== History Management ==========

def load_history() -> list:
    """加载历史记录"""
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []


def save_history(history: list):
    """保存历史记录"""
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def update_history(
    price: float,
    sotp_price: float,
    dcf_price: float,
    weighted_price: float,
    revenue: Optional[float] = None,
    net_profit: Optional[float] = None,
    upside_pct: Optional[float] = None,
) -> list:
    """更新历史记录"""
    history = load_history()

    today = date.today().isoformat()
    
    # 检查是否今天已有记录
    existing_idx = None
    for i, rec in enumerate(history):
        if rec.get('date', '') == today:
            existing_idx = i
            break

    record = {
        'date': today,
        'stock_price': price,
        'sotp_price': sotp_price,
        'dcf_price': dcf_price,
        'weighted_price': weighted_price,
        'upside_pct': upside_pct,
        'timestamp': datetime.now().isoformat(),
    }

    if revenue:
        record['revenue'] = revenue
    if net_profit:
        record['net_profit'] = net_profit

    if existing_idx is not None:
        history[existing_idx] = record
    else:
        history.append(record)

    # 保留最近365天
    if len(history) > 365:
        history = history[-365:]

    save_history(history)
    return history


# ========== Main ==========

def main():
    from stocks.09988_alibaba import model as alibaba_model

    print("=" * 60)
    print(f"阿里巴巴(HK09988) 每日数据采集")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    # 1. 获取实时股价
    print("\n📊 获取实时股价...")
    price = get_realtime_price()
    if price:
        print(f"  ✅ 股价: {price:.2f}港元")
    else:
        # 使用参考价
        import yaml
        config_path = WORK_DIR / 'stocks' / '09988_alibaba' / 'manual_data.yaml'
        try:
            with open(config_path, 'r') as f:
                data = yaml.safe_load(f)
            price = data.get('market', {}).get('current_price', 95.0)
            print(f"  ⚠️ 使用参考价: {price:.2f}港元")
        except:
            price = 95.0
            print(f"  ⚠️ 使用默认价: {price:.2f}港元")

    # 2. 运行估值模型
    print("\n🧮 运行估值模型...")
    sotp_r, dcf_r = alibaba_model.run_valuation(current_price=price)

    sotp_price = sotp_r['目标价_中枢_元']
    dcf_price = dcf_r['目标价_元']
    weighted_price = sotp_r.get('加权目标价_元', sotp_price)
    upside_pct = sotp_r['上涨空间_中枢_%']

    print(f"  SOTP: {sotp_price:.1f}港元")
    print(f"  DCF: {dcf_price:.1f}港元")
    print(f"  加权: {weighted_price:.1f}港元")
    print(f"  上涨空间: {upside_pct:+.0f}%")

    # 3. 获取财务数据
    print("\n📈 获取财务数据...")
    fin_data = get_financial_data()
    revenue = None
    net_profit = None
    if fin_data:
        try:
            # 解析EastMoney数据格式
            if isinstance(fin_data, dict):
                data_list = fin_data.get('data', []) or []
                for item in data_list:
                    if item.get('report_date', '').startswith('2024'):
                        revenue = item.get('total_revenue', None)
                        net_profit = item.get('parent_netprofit', None)
                        break
        except Exception as e:
            print(f"  ⚠️ 财务数据解析失败: {e}")

    # 4. 更新历史
    print("\n💾 更新历史数据...")
    history = update_history(
        price=price,
        sotp_price=sotp_price,
        dcf_price=dcf_price,
        weighted_price=weighted_price,
        revenue=revenue,
        net_profit=net_profit,
        upside_pct=upside_pct,
    )
    print(f"  ✅ 历史记录已更新 (共{len(history)}条)")

    print("\n" + "=" * 60)
    print("✅ 每日采集完成!")
    print("=" * 60)


if __name__ == '__main__':
    main()
