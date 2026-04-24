import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import requests
from datetime import datetime

# --- 1. 核心即時價與成交量 (精確到 2E 計算) ---
def get_realtime_data(stock_id):
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        v_match = re.search(r'"regularMarketVolume":\s*([0-9,.]+)', response.text)
        if p_match and v_match:
            price = float(p_match.group(1))
            volume = float(v_match.group(1).replace(',', ''))
            vol_amt = (volume * price) / 100000000
            return price, vol_amt
    except: pass
    return None, 0

# --- 2. 三竹 MTM 動能邏輯 (修正 yfinance 多層索引問題) ---
def check_momentum(code, p_curr):
    suffix = ".TW" if len(code) <= 4 else ".TWO"
    # 下載 1 個月數據確保足夠計算 MA10 of MTM10
    df = yf.download(f"{code}{suffix}", period="1mo", progress=False)
    
    if df.empty or len(df) < 15:
        return None, 0, False

    # 關鍵修正：處理 yfinance 的新版 DataFrame 格式
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    # 組合收盤價
    prices = df['Close'].dropna().tolist()
    prices.append(p_curr)
    
    # 計算 MTM(10)
    mtm_list = []
    for i in range(10, len(prices)):
        mtm_list.append(prices[i] - prices[i-10])
    
    if len(mtm_list) < 10: return None, 0, False
    
    curr_mtm = mtm_list[-1]
    mtm_ma = sum(mtm_list[-10:]) / 10
    
    # 轉強定義：MTM > 0 且高於均線
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma
    return round(curr_mtm, 2), round(mtm_ma, 2), is_strong

# --- 3. 讀取 CSV ---
@st.cache_data
def get_all_codes():
    all_codes = []
    files = ["TWSE.csv", "TPEX.csv"]
    for f in files:
        if os.path.exists(f):
            try:
                df = pd.read_csv(f, encoding='utf-8-sig')
            except:
                df = pd.read_csv(f, encoding='cp950')
            codes = df.iloc[:, 0].astype(str).str.strip().tolist()
            all_codes.extend([c for c in codes if c.isdigit()])
    return list(set(all_codes))

# --- 4. UI 介面 ---
st.set_page_config(page_title="動能一鍵掃描測試", layout="wide")
st.title("⚡ 三竹動能一鍵掃描 (2E 准入修正版)")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# 側邊欄控制
st.sidebar.header("控制台")
scan_btn = st.sidebar.button("📡 啟動全市場一鍵掃描")

if scan_btn:
    all_stocks = get_all_codes()
    if not all_stocks:
        st.error("找不到 CSV 檔案或代碼，請確認 TWSE.csv 是否在資料夾內。")
    else:
        results = []
        progress_text = st.empty()
        bar = st.progress(0)
        
        total = len(all_stocks)
        for i, code in enumerate(all_stocks):
            # 每掃 20 檔更新一次文字，避免畫面過於閃爍
            if i % 10 == 0:
                progress_text.text(f"正在檢查市場進度: {i}/{total}")
            bar.progress((i + 1) / total)
            
            p_curr, vol_amt = get_realtime_data(code)
            
            # --- 2E 准入條件 ---
            if p_curr and vol_amt >= 2.0:
                mtm, mtm_ma, is_strong = check_momentum(code, p_curr)
                if is_strong:
                    results.append({
                        "代碼": code,
                        "現價": p_curr,
                        "成交值(億)": round(vol_amt, 2),
                        "MTM": mtm,
                        "MTM_MA": mtm_ma,
                        "狀態": "🚀 轉強"
                    })
        
        bar.empty()
        progress_text.empty()

        if results:
            st.session_state.scan_results = pd.DataFrame(results)
        else:
            st.session_state.scan_results = "EMPTY"

# --- 5. 顯示結果 (修正報錯點) ---
if st.session_state.scan_results is not None:
    if isinstance(st.session_state.scan_results, pd.DataFrame):
        st.subheader(f"📊 掃描完成 - 發現 {len(st.session_state.scan_results)} 檔符合條件標的")
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
    elif st.session_state.scan_results == "EMPTY":
        st.warning("當前市場無符合「成交值>2E 且 動能轉強」之標的")
