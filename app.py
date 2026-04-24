import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 核心計算：三竹動能 MTM (10, 10) ---
def calculate_mtm_logic(df, p_curr):
    """
    Day=10: 計算 10 日前價格變化
    MA=10: 計算 MTM 的 10 日均線
    Precision: 2 (四捨五入到二位)
    """
    # 需要至少 20 幾天的數據才能算 MTM 的 MA10
    if len(df) < 22: return 0, 0, False, 0
    
    prices = df['Close'].dropna().tolist()
    # 結合歷史與即時價格
    full_prices = prices[:-1] + [p_curr]
    
    # 1. 計算 MTM 序列: Price(t) - Price(t-10)
    mtm_list = []
    for i in range(10, len(full_prices)):
        mtm_list.append(full_prices[i] - full_prices[i-10])
    
    current_mtm = round(mtm_list[-1], 2)
    mtm_ma10 = round(sum(mtm_list[-10:]) / 10, 2)
    
    # 2. 計算 PROC (變動率%)
    p_10_days_ago = full_prices[-11]
    proc = round((current_mtm / p_10_days_ago) * 100, 2) if p_10_days_ago != 0 else 0
    
    # 3. 判定動能轉強 (三竹邏輯: MTM 線在 MTM 均線之上)
    is_strong = current_mtm > mtm_ma10 and current_mtm > 0
    return current_mtm, proc, is_strong, mtm_ma10

# --- 1. 即時價格抓取 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', resp.text)
        if m: return float(m.group(1))
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code):
    return yf.download(code, period="3mo", progress=False)

# --- 2. 介面配置 ---
st.set_page_config(page_title="🏹 姊布林動能雷達", layout="wide")
st_autorefresh(interval=180000, key="auto_refresh")

# --- 3. 掃描邏輯 ---
def run_momentum_scan(codes, is_auto=False):
    results = []
    m_env = get_market_env() # 假設此處沿用你原本的大盤環境函數
    
    prog = st.progress(0, text="準備掃描...")
    total = len(codes)
    
    for i, code in enumerate(codes):
        prog.progress((i+1)/total, text=f"分析中: {code}")
        
        # 1. 抓取歷史數據
        df = get_historical_data(f"{code}.TW")
        m_type = "上市"
        if df.empty:
            df = get_historical_data(f"{code}.TWO")
            m_type = "上櫃"
        
        if df.empty or len(df) < 25: continue
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        # 2. 取得即時價與今日漲幅
        p_yest = float(df['Close'].iloc[-1])
        p_curr = get_realtime_price(code)
        if not p_curr: p_curr = p_yest
        
        chg = (p_curr - p_yest) / p_yest
        vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
        
        # --- ⚡ 篩選門檻 (這裡調鬆，確保能看到東西) ---
        # 如果是自動掃描全市場，門檻：有漲 (chg > 0) 且 成交值 > 1 億
        if is_auto:
            if chg <= 0.01 or vol_amt < 1.0: continue 

        # 3. 計算三竹 MTM 邏輯
        mtm, proc, is_strong, mtm_ma = calculate_mtm_logic(df, p_curr)
        
        # 動能不夠強的標的在自動掃描中過濾掉
        if is_auto and not is_strong: continue

        # 4. 姊布林 ABCDE 策略判定 (簡化判定以供快速比對)
        # 這裡插入你原本的 bw, upper, slope 判定邏輯...
        # 為示範先標註「僅動能強」
        res_tag = "⚪ 僅動能強" 
        # (此處省略你原本那一長串的 if-else 邏輯，請記得保留在你程式碼中)

        results.append({
            "代號": code,
            "名稱": stock_info_map.get(code, {}).get("簡稱", "-"),
            "動能(PROC%)": f"{proc}%",
            "MTM值": mtm,
            "MTM均線": mtm_ma,
            "策略": res_tag,
            "現價": p_curr,
            "漲幅%": f"{chg*100:.2f}%",
            "成交值(億)": round(vol_amt, 2)
        })
    
    prog.empty()
    return results

# --- 4. 側邊欄與按鈕 ---
st.sidebar.title("🛠️ 設定區")
if st.sidebar.button("📡 啟動全市場動能掃描"):
    all_codes = list(stock_info_map.keys()) # 從你的 CSV 載入的清單
    scan_res = run_momentum_scan(all_codes, is_auto=True)
    if scan_res:
        st.session_state.scan_results = pd.DataFrame(scan_res)
    else:
        st.warning("符合條件的動能股目前為 0，請檢查市場狀態或調鬆參數。")

# 顯示結果
if st.session_state.get("scan_results") is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
