import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# ==========================================
# /scaffold: 系統核心配置與環境初始化
# ==========================================
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# --- 介面美化函數 ---
def set_ui_style(image_file):
    """
    /optimize: 透過 Base64 編碼優化背景載入速度，減少渲染延遲。
    """
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); z-index: -1; }}
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.85) !important; border-radius: 10px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)
set_ui_style("header_image.png")

# ==========================================
# /optimize: 高效數據抓取模組 (Vectorization Ready)
# ==========================================
@st.cache_data(ttl=10) 
def get_realtime_price(stock_id):
    """抓取 Yahoo Finance 即時價格"""
    target = '%5ETWOII' if stock_id == 'OTC' else ('%5ETWII' if stock_id == 'TSE' else stock_id)
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        if match: return float(match.group(1))
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    """抓取歷史 K 線數據"""
    return yf.download(code_with_suffix, period="2mo", progress=False)

# ==========================================
# /refactor: 數據清洗與族群對應模組
# ==========================================
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name, market_label in [("TWSE.csv", "上市"), ("TPEX.csv", "上櫃")]:
        if os.path.exists(f_name):
            try:
                try: df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df_local = pd.read_csv(f_name, encoding='cp950')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "市場": market_label,
                            "產業排位": str(row.iloc[2]).strip() if len(row)>2 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row)>4 else "-"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# ==========================================
# /new_strategy: 營收動能策略 (核心修正版)
# 邏輯：同資料夾過濾關鍵字 + 檔案倒序排序
# ==========================================
def run_revenue_momentum_strategy():
    folder = "revenue_data"
    if not os.path.exists(folder):
        st.error(f"❌ 找不到資料夾: {folder}")
        return None

    all_results = []
    # 定義市場關鍵字與對應後綴
    market_configs = [
        {"key": "TWSE", "label": "上市", "suffix": ".TW"},
        {"key": "TPEX", "label": "上櫃", "suffix": ".TWO"}
    ]

    for m_cfg in market_configs:
        # /refactor: 僅抓取檔名包含特定市場關鍵字的檔案
        market_files = [f for f in glob.glob(os.path.join(folder, "*.csv")) if m_cfg["key"] in os.path.basename(f)]
        
        # /optimize: 強制依檔名倒序排序，確保首位為最新月份
        market_files.sort(reverse=True)
        
        if len(market_files) < 3:
            st.warning(f"⚠️ {m_cfg['label']} 檔案不足 3 個，略過掃描。")
            continue
        
        recent_files = market_files[:3]
        month_dfs = []
        
        for f in recent_files:
            try:
                try: t_df = pd.read_csv(f, encoding='utf-8-sig')
                except: t_df = pd.read_csv(f, encoding='cp950')
                t_df.columns = [c.strip() for c in t_df.columns]
                
                # 篩選核心欄位
                if all(col in t_df.columns for col in ['公司代號', '公司名稱', '營業收入-去年同月增減(%)']):
                    temp = t_df[['公司代號', '公司名稱', '營業收入-去年同月增減(%)']].copy()
                    temp.columns = ['ID', 'Name', 'YoY']
                    temp['ID'] = temp['ID'].astype(str).str.strip()
                    temp['YoY'] = pd.to_numeric(temp['YoY'], errors='coerce')
                    month_dfs.append(temp.drop_duplicates('ID'))
            except: continue

        if len(month_dfs) == 3:
            # /explain_math: 計算平均增長率
            # $$AvgGrowth = \frac{YoY_1 + YoY_2 + YoY_3}{3}$$
            m1, m2, m3 = month_dfs[0], month_dfs[1], month_dfs[2]
            merged = m1.merge(m2[['ID', 'YoY']], on='ID', suffixes=('', '2'))
            merged = merged.merge(m3[['ID', 'YoY']], on='ID', suffixes=('', '3'))
            merged['avg_growth'] = (merged['YoY'] + merged['YoY2'] + merged['YoY3']) / 3
            
            # 濾選平均年增 > 20%
            targets = merged[merged['avg_growth'] > 20].copy()
            
            for _, row in targets.iterrows():
                code = row['ID']
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                df_h = get_historical_data(f"{code}{m_cfg['suffix']}")
                if not df_h.empty:
                    if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                    p_yest = float(df_h['Close'].iloc[-1])
                    chg = (p_curr - p_yest) / p_yest
                    vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                    
                    info = stock_info_map.get(code, {})
                    all_results.append({
                        "市場": m_cfg['label'],
                        "代號": code, "名稱": row['Name'], 
                        "三月均年增%": f"{row['avg_growth']:.1f}%",
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", 
                        "成交值(億)": round(vol_amt, 1),
                        "族群細分": info.get("族群細分", "-")
                    })
    return pd.DataFrame(all_results) if all_results else None

# ==========================================
# /main: 應用程式主迴圈
# ==========================================
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

if not st.session_state.password_correct:
    st.title("🔒 系統存取控制")
    pwd = st.text_input("輸入開發者密碼", type="password")
    if st.button("驗證"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
    st.stop()

# 側邊欄策略選擇
mode = st.sidebar.radio("📡 選擇策略模式", ["姊布林 ABCDE", "營收動能策略"])

if mode == "營收動能策略":
    st.header("📊 營收動能掃描 (YoY > 20%)")
    if st.button("🚀 執行雙市場同步掃描"):
        with st.spinner("正在進行關鍵字過濾與數據回測..."):
            res = run_revenue_momentum_strategy()
            if res is not None:
                st.session_state.scan_results = res
            else:
                st.info("當前無符合條件之標的。")

# 顯示結果表格
if st.session_state.scan_results is not None:
    st.subheader("📋 策略掃描結果")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# /commit_msg: "feat: integrate revenue momentum with keyword filtering and sorting"
