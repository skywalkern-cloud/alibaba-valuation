#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿里巴巴(HK09988) 估值仪表盘 v1.0
Streamlit Cloud部署版

功能:
- 实时股价 + 估值足球场
- SOTP分部估值明细
- 历史趋势图
- DCF双变量敏感度热力图
- 上涨空间柱状图
"""

import streamlit as st
import pandas as pd
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from common.core.discounting_engine import DiscountingEngine
from stocks.09988_alibaba import model as alibaba_model

# ========== Page Config ==========
st.set_page_config(
    page_title="阿里巴巴(09988) 估值仪表盘",
    page_icon="🐉",
    layout="wide",
)

# ========== Custom CSS ==========
st.markdown("""
<style>
    .main-header {
        font-size: 1.8rem;
        font-weight: 700;
        color: #fff;
        background: linear-gradient(135deg, #ff6a00, #ff0000);
        padding: 1rem 1.5rem;
        border-radius: 12px;
        margin-bottom: 1.5rem;
    }
    .section-header {
        font-size: 1.2rem;
        font-weight: 600;
        color: #ff6a00;
        margin: 1.5rem 0 1rem 0;
        padding-bottom: 0.3rem;
        border-bottom: 2px solid #ff6a00;
    }
    .price-card {
        background: linear-gradient(135deg, #667eea, #764ba2);
        padding: 1.5rem;
        border-radius: 12px;
        color: white;
        text-align: center;
    }
    .upside-green { color: #4CAF50; font-weight: 700; }
    .upside-red { color: #f44336; font-weight: 700; }
    .stMetric {
        background: #f8f9fa;
        padding: 1rem;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# ========== Data Loading ==========

@st.cache_data(ttl=300)
def get_realtime_price() -> float:
    """获取港股实时股价"""
    try:
        import akshare as ak
        df = ak.hk_stock_spot_em()
        # 找09988
        row = df[df['代码'] == '09988']
        if not row.empty:
            price = float(row['最新价'].values[0])
            if price > 0:
                return price
    except Exception as e:
        pass
    # Fallback
    return 95.0


@st.cache_data(ttl=3600)
def load_history() -> pd.DataFrame:
    """从 data/history.json 读取历史数据"""
    path = Path(__file__).parent / 'data' / 'history.json'
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        df = pd.DataFrame(data)
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            df = df.sort_values('date').set_index('date')
        return df
    return pd.DataFrame()


# ========== Soccer Field Chart ==========

def render_soccer_field(prices: Dict[str, float], current_price: float):
    """渲染足球场估值图"""
    st.markdown('<p class="section-header">⚽ 估值足球场</p>', unsafe_allow_html=True)

    labels = list(prices.keys())
    values = list(prices.values())

    try:
        import altair as alt

        df = pd.DataFrame({
            "估值方法": labels,
            "目标价(港元)": values,
        })

        chart = alt.Chart(df).mark_bar(opacity=0.85).encode(
            x=alt.X('估值方法', sort=None, title=''),
            y=alt.Y('目标价(港元)', title='目标价 (HKD)'),
            color=alt.condition(
                alt.datum['目标价(港元)'] > current_price,
                alt.value('#4CAF50'),
                alt.value('#f44336')
            ),
            tooltip=['估值方法', '目标价(港元)']
        ).properties(height=280)

        text = alt.Chart(df).mark_text(dy=-12, size=13, color='black', fontWeight='bold').encode(
            x='估值方法',
            y='目标价(港元):Q',
            text=alt.Text('目标价(港元):Q', format='.1f')
        )

        st.altair_chart(chart + text, use_container_width=True)

    except:
        st.bar_chart(pd.DataFrame({'估值方法': labels, '目标价(港元)': values}).set_index('估值方法'))


# ========== SOTP Detail Table ==========

def render_sotp_table(sotp_result: Dict[str, Any], current_price: float):
    """渲染SOTP明细表"""
    st.markdown('<p class="section-header">📊 SOTP分部估值明细</p>', unsafe_allow_html=True)

    divisions = sotp_result.get('分部列表', [])

    if not divisions:
        st.info("暂无分部数据")
        return

    rows = []
    for div in divisions:
        min_val, max_val = div.get('分部市值_亿_区间', (0, 0))
        mid_val = (min_val + max_val) / 2
        rows.append({
            '业务分部': div.get('name', div.get('name', 'N/A')),
            '净利润(亿)': f"{div.get('分部净利润_亿', 0):.1f}",
            'PE区间': div.get('PE区间', 'N/A'),
            'PE中枢': f"{div.get('PE_base', 0):.0f}x",
            '市值(亿港元)': f"{min_val:.0f}~{max_val:.0f}",
            '市值中枢(亿)': f"{mid_val:.0f}",
        })

    df = pd.DataFrame(rows)

    # 合计行
    total_min = sum(div.get('分部市值_亿_区间', (0, 0))[0] for div in divisions)
    total_max = sum(div.get('分部市值_亿_区间', (0, 0))[1] for div in divisions)
    total_mid = (total_min + total_max) / 2
    total_nm = sum(div.get('分部净利润_亿', 0) for div in divisions)

    total_df = pd.DataFrame([{
        '业务分部': '📌 合计',
        '净利润(亿)': f"{total_nm:.1f}",
        'PE区间': '-',
        'PE中枢': f"{total_mid/total_nm:.0f}x" if total_nm > 0 else '-',
        '市值(亿港元)': f"{total_min:.0f}~{total_max:.0f}",
        '市值中枢(亿)': f"{total_mid:.0f}",
    }])

    df_display = pd.concat([df, total_df], ignore_index=True)

    st.dataframe(
        df_display.style.set_properties(**{
            'text-align': 'center'
        }),
        use_container_width=True,
        hide_index=True
    )

    sotp_mid = sotp_result.get('目标价_中枢_元', 0) or sotp_result.get('目标价_元', 0)
    sotp_min = sotp_result.get('目标价_区间_元', (0, 0))[0] if sotp_result.get('目标价_区间_元') else 0
    sotp_max = sotp_result.get('目标价_区间_元', (0, 0))[1] if sotp_result.get('目标价_区间_元') else 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("SOTP中枢", f"{sotp_mid:.1f}港元", 
                  delta=f"{(sotp_mid/current_price-1)*100:.0f}%" if current_price > 0 else None)
    with c2:
        st.metric("SOTP区间", f"{sotp_min:.1f}~{sotp_max:.1f}港元")
    with c3:
        st.metric("当前价", f"{current_price:.1f}港元")
    with c4:
        upside = (sotp_mid / current_price - 1) * 100 if current_price > 0 else 0
        st.metric("上涨空间", f"{upside:+.0f}%", 
                  delta_color="normal" if upside > 0 else "inverse")


# ========== Historical Trend ==========

def render_trend(df: pd.DataFrame):
    """渲染历史趋势图"""
    st.markdown('<p class="section-header">📈 历史趋势</p>', unsafe_allow_html=True)

    if df.empty:
        st.info("📋 暂无历史数据。每日cron任务运行后会写入数据到 data/history.json")
        return

    try:
        import altair as alt

        tabs = st.tabs(["股价vs目标价", "上涨空间", "营收/利润"])

        with tabs[0]:
            if 'stock_price' in df.columns:
                price_cols = ['stock_price']
                for c in ['sotp_price', 'dcf_price', 'weighted_price']:
                    if c in df.columns:
                        price_cols.append(c)
                price_df = df[price_cols].dropna().reset_index()
                long_df = price_df.melt('date', var_name='指标', value_name='价格(HKD)')

                chart = alt.Chart(long_df).mark_line(point=True).encode(
                    x='date:T', y='价格(HKD):Q', color='指标:N'
                ).properties(height=220)

                st.altair_chart(chart, use_container_width=True)

        with tabs[1]:
            if 'upside_pct' in df.columns:
                up_df = df[['upside_pct', 'stock_price']].dropna().reset_index()
                up_df.columns = ['date', '上涨空间(%)', '股价']
                bar_df = up_df.copy()
                bar_df['color'] = ['#4CAF50' if x > 0 else '#f44336' for x in bar_df['上涨空间(%)']]

                chart = alt.Chart(bar_df).mark_bar().encode(
                    x='date:T', y='上涨空间(%):Q', color=alt.Color('上涨空间(%):Q', scale=alt.Scale(scheme='redyellowgreen'))
                ).properties(height=200)
                st.altair_chart(chart, use_container_width=True)

        with tabs[2]:
            if 'revenue' in df.columns:
                rev_df = df[['revenue', 'net_profit']].dropna().reset_index()
                rev_df.columns = ['date', '营收(亿)', '净利润(亿)']
                long_df = rev_df.melt('date', var_name='指标', value_name='金额(亿)')
                chart = alt.Chart(long_df).mark_line(point=True).encode(
                    x='date:T', y='金额(亿):Q', color='指标:N'
                ).properties(height=200)
                st.altair_chart(chart, use_container_width=True)

    except Exception as e:
        st.warning(f"图表渲染降级: {e}")
        if 'stock_price' in df.columns:
            price_cols = ['stock_price']
            for c in ['sotp_price', 'dcf_price']:
                if c in df.columns:
                    price_cols.append(c)
            st.line_chart(df[price_cols])


# ========== DCF Sensitivity Heatmap ==========

def render_dcf_heatmap(fcf_proj: List[float], shares: float, net_debt: float = 0):
    """渲染DCF双变量敏感度热力图"""
    st.markdown('<p class="section-header">🌡️ DCF双变量敏感度 (Terminal Growth × WACC)</p>', unsafe_allow_html=True)

    engine = DiscountingEngine()

    tg_vals = [0.02, 0.03, 0.04]
    wacc_base = engine.calc_wacc()

    wacc_low = round((wacc_base - 0.02) * 100, 1)
    wacc_mid = round(wacc_base * 100, 1)
    wacc_high = round((wacc_base + 0.02) * 100, 1)
    wacc_vals = [wacc_base - 0.02, wacc_base, wacc_base + 0.02]

    rows = []
    for tg in tg_vals:
        row = []
        for w in wacc_vals:
            r = engine.dcf_fcf(fcf_proj, fcf_proj[-1], w, net_debt, shares, tg)
            row.append(r['目标价_元'])
        rows.append(row)

    col_labels = [f"WACC={w*100:.1f}%" for w in wacc_vals]
    row_labels = [f"TG={t*100:.0f}%" for t in tg_vals]

    heat_df = pd.DataFrame(rows, index=row_labels, columns=col_labels)

    st.dataframe(
        heat_df.style.background_gradient(cmap="RdYlGn", axis=None)
                .format("{:.1f}"),
        use_container_width=True
    )
    st.caption(f"WACC基准: {wacc_mid:.1f}% (Rf=3.5%, β=0.9) | 单位: 港元")


# ========== Upside Bar Chart ==========

def render_upside_bar(prices: Dict[str, float], current_price: float):
    """渲染上涨空间柱状图"""
    st.markdown('<p class="section-header">🚀 上涨空间对比</p>', unsafe_allow_html=True)

    upsi = {k: (v / current_price - 1) * 100 for k, v in prices.items() if current_price > 0}

    try:
        import altair as alt

        df = pd.DataFrame({
            '方法': list(upsi.keys()),
            '上涨空间(%)': list(upsi.values()),
        })
        df['颜色'] = ['#4CAF50' if x > 0 else '#f44336' for x in df['上涨空间(%)']]

        chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('方法', sort=None),
            y='上涨空间(%):Q',
            color=alt.Color('上涨空间(%):Q', scale=alt.Scale(scheme='redyellowgreen')),
            tooltip=['方法', '上涨空间(%)']
        ).properties(height=220)

        text = alt.Chart(df).mark_text(dy=-10, size=12, color='black', fontWeight='bold').encode(
            x='方法',
            y='上涨空间(%):Q',
            text=alt.Text('上涨空间(%):Q', format='.0f')
        )

        st.altair_chart(chart + text, use_container_width=True)

    except:
        st.bar_chart(pd.DataFrame({'上涨空间(%)': upsi}))


# ========== Main ==========

def main():
    # Header
    st.markdown(
        '<div class="main-header">'
        '🐉 阿里巴巴(09988) 估值仪表盘'
        '</div>',
        unsafe_allow_html=True
    )

    # Load data
    current_price = get_realtime_price()
    df_history = load_history()

    # Sidebar controls
    with st.sidebar:
        st.header("⚙️ 估值参数")
        rf = st.slider("无风险利率(Rf)", 0.01, 0.06, 0.035, 0.005, format="%.3f")
        beta = st.slider("Beta系数", 0.5, 1.5, 0.9, 0.05)
        tg = st.slider("永续增长率(TG)", 0.01, 0.06, 0.04, 0.005, format="%.2f")

        engine = DiscountingEngine()
        wacc = engine.calc_wacc(rf, beta)

        st.write(f"**WACC: {wacc*100:.2f}%**")
        st.write(f"**当前价: {current_price:.2f}港元**")

        st.markdown("---")
        st.markdown("**📂 数据来源**")
        st.markdown("- 股价: akshare (实时)")
        st.markdown("- 历史: data/history.json")
        st.markdown("- 财报: EastMoney API")
        st.markdown("---")
        st.markdown(f"[GitHub](https://github.com/skywalkern-cloud/alibaba-valuation)")

    # Run valuation model
    sotp_result, dcf_result = alibaba_model.run_valuation(
        rf=rf, beta=beta, tg=tg
    )

    sotp_mid = sotp_result.get('目标价_中枢_元', sotp_result.get('目标价_元', 0))
    sotp_min = sotp_result.get('目标价_区间_元', (0, 0))[0] if sotp_result.get('目标价_区间_元') else 0
    sotp_max = sotp_result.get('目标价_区间_元', (0, 0))[1] if sotp_result.get('目标价_区间_元') else 0
    dcf_price = dcf_result.get('目标价_元', 0)
    weighted_price = sotp_result.get('加权目标价_元', dcf_price)

    # PE-based price targets (HKD)
    pe15_price = current_price * 0.85
    pe20_price = current_price * 1.0
    pe25_price = current_price * 1.15

    prices = {
        "SOTP中枢": sotp_mid,
        "DCF": dcf_price,
        "概率加权": weighted_price,
        "PE×15": pe15_price,
        "PE×20": pe20_price,
        "PE×25": pe25_price,
        "当前价": current_price,
    }

    # Layout
    col_trend, col_sotp = st.columns([1, 1])

    with col_trend:
        render_trend(df_history)

    with col_sotp:
        render_sotp_table(sotp_result, current_price)

    st.markdown("---")
    col1, col2 = st.columns([1, 1])

    with col1:
        render_soccer_field(prices, current_price)

    with col2:
        render_upside_bar(prices, current_price)

    st.markdown("---")
    render_dcf_heatmap(
        sotp_result.get('fcf_projections', [60, 75, 90, 105, 120]),
        sotp_result.get('shares', 47.5),
        sotp_result.get('net_debt', 0)
    )

    # Footer
    st.markdown("---")
    st.caption(
        f"最后更新: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        "数据由每日cron任务自动更新 | "
        "[GitHub](https://github.com/skywalkern-cloud/alibaba-valuation)"
    )


if __name__ == '__main__':
    main()
