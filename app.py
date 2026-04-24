import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 核心動能計算 (對齊三竹 SDK: Day=10, MA=10) ---
def calculate_mtm_sdk(df, p_curr):
    if df is None or len(df) < 22: return 0, 0, False
    
    # 取得歷史收盤價並加入今日即時價
    prices = df['Close'].dropna().tolist()
    # 確保只取到昨天，然後加上今天即時價
    full_prices = prices + [p_curr]
    
    # 計算 MTM (10): 當前價 - 10日前價
    mtm_series = []
    for i in range(10, len(full_prices)):
        mtm_series.append(full_prices[i] - full_prices[i-10])
    
    if len(mtm_series) < 10: return 0, 0, False
    
    curr_mtm = round(mtm_series[-1], 2)
    mtm_ma10 = sum(mtm_series[-10:]) / 10
    
    # PROC (變動率): (MTM / 10日前價格) * 100
    p_10_days_ago = full_prices[-11]
    proc = round((curr_mtm / p_10_days_ago) * 100, 2) if p_10_days_ago != 0 else 0
    
    # 轉強判定: MTM > 0 且 MTM 在 MTM均線之上
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma10
    return curr_mtm, proc, is_strong

# --- 0.1 即時價格爬蟲 ---
def get_realtime_price(stock_id):
    target = stock_id
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', resp.text)
        if m: return float(m.group(1).replace(',', ''))
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code):
    # 下載最近一個月的日線數據
    return yf.download(code, period="1mo", progress=False)

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 姊布林戰情室", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# --- 2. 🛡️ 載入 CSV 資料 (沿用你原本的邏輯) ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業": str(row.iloc[2]).strip() if len(row)>2 else "-"}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 3. 處理掃描核心 ---
def run_process(codes, filter_mode=False):
    results = []
    # 增加進度條回饋
    progress_bar = st.progress(0)
    for i, code in enumerate(codes):
        if filter_mode: progress_bar.progress((i + 1) / len(codes))
        
        # 抓取數據
        p_curr = get_realtime_price(code)
        if not p_curr: continue
        
        df = get_historical_data(f"{code}.TW")
        if df.empty: df = get_historical_data(f"{code}.TWO")
        if df.empty or len(df) < 15: continue
        
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        p_yest = float(df['Close'].iloc[-1])
        chg = (p_curr - p_yest) / p_yest
        
        # 🔥 修正成交值計算 (張數 * 股價 * 1000 / 1億)
        vol_amt = (df['Volume'].iloc[-1] * p_curr * 1000) / 100000000
        
        # 計算動能
        mtm, proc, is_strong = calculate_mtm_sdk(df, p_curr)
        
        # --- 如果是「全市場掃描」模式，才執行嚴格過濾 ---
        if filter_mode:
            if chg < 0.02: continue # 漲幅 > 2%
            if vol_amt < 2.0: continue # 成交值 > 2 億
            if not is_strong: continue # 動能轉強
            
        results.append({
            "代號": code,
            "名稱": stock_info_map.get(code, {}).get("簡稱", "台股"),
            "策略": "🚀 動能轉強" if is_strong else "⚪ 觀察",
            "現價": p_curr,
            "漲幅%": f"{chg*100:.2f}%",
            "成交值(億)": round(vol_amt, 2),
            "MTM(10)": mtm,
            "PROC%": proc
        })
    progress_bar.empty()
    return results

# --- 4. 側邊欄 ---
st.sidebar.title("🛠️ 戰情控制")
raw_input = st.sidebar.text_area("1. 手動輸入代碼 (不限漲幅成交量)", placeholder="2330 2317")
if st.sidebar.button("🔍 搜尋指定清單"):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    if codes:
        st.session_state.scan_results = pd.DataFrame(run_process(codes, filter_mode=False))

st.sidebar.markdown("---")
if st.sidebar.button("📡 啟動全市場動能掃描"):
    all_codes = list(stock_info_map.keys())
    # filter_mode=True 會執行 漲幅>2%, 成交>2億, 動能轉強
    res = run_process(all_codes, filter_mode=True)
    if res:
        st.session_state.scan_results = pd.DataFrame(res)
    else:
        st.sidebar.warning("當前市場無符合標的。")

# --- 5. 顯示 ---
if st.session_state.scan_results is not None:
    st.subheader(f"📊 掃描結果 (共 {len(st.session_state.scan_results)} 檔)")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
