import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 1. 🏎️ 高效能快取與數據獲取 ---

@st.cache_data(ttl=300) # 5分鐘快取，避免頻繁抓取相同代碼
def get_realtime_price(stock_id):
    """
    改進邏輯：增加市場後綴自動判定，提升抓取成功率
    """
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        patterns = [r'"regularMarketPrice":\s*([0-9.]+)', r'"price":\s*"([0-9,.]+)"']
        for p in patterns:
            match = re.search(p, response.text)
            if match:
                val = float(match.group(1).replace(',', ''))
                if val > 0: return val
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    """
    快取機制：歷史數據一小時更新一次即可
    """
    return yf.download(code_with_suffix, period="3mo", progress=False)

# --- 2. 🛡️ 數據預處理與預過濾 ---

@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    # 預過濾：確保檔案存在才讀取，並標記市場別
    for f_name, market_label in [("TWSE.csv", "上市"), ("TPEX.csv", "上櫃")]:
        if os.path.exists(f_name):
            try:
                df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                df_local = df_local.fillna('-')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "市場": market_label,  # 🚀 新增：欄位加上市場別
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping

# --- 3. 核心邏輯修正：改進計算邏輯 (避免未來函數) ---

def calculate_indicators(df, p_curr):
    """
    改進計算邏輯：確保當前即時價格 p_curr 與歷史 Close 序列正確銜接
    """
    if isinstance(df.columns, pd.MultiIndex): 
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=['Close'])
    
    # 邏輯修正：判斷今日 K 線是否已在歷史數據中 (盤後與盤中差異)
    today_date = datetime.now().date()
    if df.index[-1].date() >= today_date:
        # 如果 yfinance 已經抓到今日，則取前 19 天 + 當前即時價
        history_for_ma = df['Close'].iloc[-20:-1].tolist()
        p_yest = float(df['Close'].iloc[-2])
    else:
        # 如果 yfinance 尚未更新今日，則取前 19 天 + 當前即時價
        history_for_ma = df['Close'].iloc[-19:].tolist()
        p_yest = float(df['Close'].iloc[-1])
    
    full_series = history_for_ma + [p_curr]
    s = pd.Series(full_series)
    
    m20 = s.mean()
    std = s.std()
    upper = m20 + (std * 2)
    bw = (std * 4) / m20 if m20 != 0 else 0
    chg = (p_curr - p_yest) / p_yest
    
    # 斜率判定：今日 20MA 是否大於昨日 20MA
    m20_yest = sum(history_for_ma) / len(history_for_ma) if history_for_ma else 0
    slope_pos = m20 > m20_yest
    
    return p_curr, chg, bw, upper, m20, slope_pos

# --- 4. Streamlit UI 執行與顯示 ---

# (中間密碼鎖與背景設定維持原樣，略)

stock_info_map = get_stock_info_full()

# 策略掃描部分修正
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        
        with st.spinner("核心邏輯計算中..."):
            for code in codes:
                # 1. 預過濾：檢查是否存在於對應市場
                info = stock_info_map.get(code)
                if not info: continue
                
                # 2. 獲取即時價格
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                # 3. 獲取歷史數據 (依據市場別後綴)
                suffix = ".TW" if info["市場"] == "上市" else ".TWO"
                df = get_historical_data(f"{code}{suffix}")
                
                if not df.empty and len(df) >= 20:
                    # 4. 執行改進後的指標計算
                    price, change, b_width, up_band, ma20, is_up = calculate_indicators(df, p_curr)
                    
                    # 交易量過濾 (億)
                    vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                    
                    # 策略標籤判定 (簡化範例)
                    res_tag = "⚪ 未達標"
                    if price > up_band and is_up and vol_amt >= 5:
                        if 0.05 <= b_width <= 0.1: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < b_width <= 0.2: res_tag = "🎯【B：海龍】"
                        elif 0.2 < b_width <= 0.4: res_tag = "🌊【C：瘋狗】"

                    results.append({
                        "代號": code,
                        "名稱": info["簡稱"],
                        "市場": info["市場"], # 🚀 欄位加上市場別
                        "策略": res_tag,
                        "現價": price,
                        "漲幅%": f"{change*100:.1f}%",
                        "成交值(億)": round(vol_amt, 1),
                        "帶寬%": f"{b_width*100:.2f}%",
                        "產業排位": info["產業排位"]
                    })

        if results:
            st.session_state.scan_results = pd.DataFrame(results)
            st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
