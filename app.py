import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests

# --- 1. 核心即時價與成交量抓取 ---
def get_realtime_data(stock_id):
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 抓價格
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        # 抓成交量 (Yahoo 這裡通常是總成交股數)
        v_match = re.search(r'"regularMarketVolume":\s*([0-9,.]+)', response.text)
        
        if p_match and v_match:
            price = float(p_match.group(1))
            volume = float(v_match.group(1).replace(',', ''))
            # 成交值計算 (股數 * 價格 / 1億)
            vol_amt = (volume * price) / 100000000
            return price, vol_amt
    except: pass
    return None, 0

# --- 2. 三竹 MTM 邏輯 (Day=10, MA=10) ---
def check_momentum(code):
    # 下載歷史數據 (需要 22 天以上來計算 MA10 of MTM10)
    suffix = ".TW" if len(code) <= 4 else ".TWO"
    df = yf.download(f"{code}{suffix}", period="1mo", progress=False)
    
    if df.empty or len(df) < 20:
        df = yf.download(f"{code}.TWO", period="1mo", progress=False)
        if df.empty: return None

    # 修正 yfinance 多層索引
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    p_curr, vol_amt = get_realtime_data(code)
    if not p_curr: return None

    # 組合收盤價序列
    prices = df['Close'].dropna().tolist()
    if len(prices) < 20: return None
    
    # 加入即時價
    prices.append(p_curr)
    
    # 計算 MTM(10) 序列: 當日價 - 10日前價
    mtm_list = []
    for i in range(10, len(prices)):
        mtm_list.append(prices[i] - prices[i-10])
    
    curr_mtm = mtm_list[-1]
    mtm_ma = sum(mtm_list[-10:]) / 10 # MTM 的 10日均線
    
    # 判定轉強：MTM > 0 且 MTM 在均線之上
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma
    
    return {
        "代碼": code,
        "現價": p_curr,
        "成交值(億)": round(vol_amt, 2),
        "MTM(10)": round(curr_mtm, 2),
        "MTM_MA(10)": round(mtm_ma, 2),
        "動能狀態": "🚀 轉強" if is_strong else "⚪ 平穩"
    }

# --- 3. 測試介面 ---
st.title("⚡ 動能參數測試模組")
st.write("此版本僅測試 **2E 准入** 與 **三竹動能參數** 是否生效")

test_input = st.text_input("輸入股票代碼測試 (如: 2330, 2317, 1513)", "2330 2317 1513")

if st.button("開始測試"):
    codes = re.findall(r'\b\d{4,6}\b', test_input)
    results = []
    
    for c in codes:
        with st.spinner(f"分析 {c}..."):
            data = check_momentum(c)
            if data:
                # 門檻測試：成交值 > 2E 且 動能轉強
                if data["成交值(億)"] >= 2.0 and data["動能狀態"] == "🚀 轉強":
                    results.append(data)
                else:
                    st.write(f"⚠️ {c} 未達標 (成交值:{data['成交值(億)']}E, 狀態:{data['動能狀態']})")
    
    if results:
        st.success("以下為符合「2E + 動能轉強」之標的：")
        st.table(results)
    else:
        st.error("目前輸入的代碼中，沒有同時符合 2E 與動能轉強的股票。")
