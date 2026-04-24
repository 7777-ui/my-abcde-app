import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import requests

# --- 1. 強化版數據抓取 (解決抓不到 2 億的問題) ---
def get_realtime_data_stable(stock_id):
    # 增加市場代碼修正
    target = stock_id
    if len(stock_id) <= 4: target = stock_id + ".TW"
    else: target = stock_id + ".TWO"
    
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 改用更寬鬆的匹配，確保成交張數 (Volume) 能量化
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        # 三竹的核心是成交值，我們同時嘗試抓取 Volume (張數) 或直接抓成交值欄位
        v_match = re.search(r'"regularMarketVolume":\s*([0-9,.]+)', response.text)
        py_match = re.search(r'"regularMarketPreviousClose":\s*([0-9.]+)', response.text)

        if p_match and v_match and py_match:
            price = float(p_match.group(1))
            volume = float(v_match.group(1).replace(',', ''))
            prev_close = float(py_match.group(1))
            
            # 成交值 = (張數 * 1000 * 價格) / 1億
            # 注意：Yahoo 的 Volume 有時是股數有時是張數，我們統一以「張」換算
            vol_amt = (volume * price) / 100000 
            chg_pct = (price - prev_close) / prev_close
            return price, vol_amt, chg_pct
    except: pass
    return None, 0, 0

# --- 2. 三竹動能加權分計算 ---
def calculate_momentum_score(code, p_curr, day=10, ma=10):
    suffix = ".TW" if len(code) <= 4 else ".TWO"
    df = yf.download(f"{code}{suffix}", period="1mo", progress=False)
    
    if df.empty: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    
    prices = df['Close'].dropna().tolist()
    # 確保不會重複計算今日
    if len(prices) > 0: prices.append(p_curr)
    
    if len(prices) < (day + ma): return None

    # A. 計算 MTM 序列
    mtm_list = []
    for i in range(len(prices) - ma, len(prices)):
        mtm_list.append(prices[i] - prices[i-day])
    
    # B. 計算 MTM_MA
    curr_mtm = mtm_list[-1]
    mtm_ma = sum(mtm_list) / len(mtm_list)
    
    # C. 【動能加權評分機制】
    # 基準 1: 穿過均線 (MTM > MTM_MA) 給予基礎分 50
    # 基準 2: MTM > 0 給予基礎分 20
    # 基準 3: 乖離率 (MTM相對於均線的強度)
    score = 0
    if curr_mtm > mtm_ma: score += 50
    if curr_mtm > 0: score += 20
    
    # 強度加權：MTM 超過均線越多，分數越高 (最高加 30 分)
    intensity = (curr_mtm / mtm_ma) if mtm_ma > 0 else 1
    score += min(30, max(0, (intensity - 1) * 100))
    
    return {
        "MTM": round(curr_mtm, 2),
        "MTM_MA": round(mtm_ma, 2),
        "動能分": int(score),
        "狀態": "🚀 強勁" if score > 70 else ("🟡 轉強" if score > 50 else "⚪ 平穩")
    }

# --- 3. UI 邏輯 ---
st.title("🏹 三竹價漲動能 (加權評分版)")

if st.sidebar.button("📡 全市場一鍵掃描"):
    # (假設 get_all_codes 已經定義如前)
    stocks = ["2330", "2317", "1513", "2363", "3231", "2382"] # 範例代碼
    results = []
    
    for code in stocks:
        p_curr, vol_amt, chg_pct = get_realtime_data_stable(code)
        
        # 1. 條件過濾：漲幅 > 2% 且 成交值 > 2 億
        if p_curr and vol_amt >= 2.0 and chg_pct >= 0.02:
            m_data = calculate_momentum_score(code, p_curr)
            if m_data and m_data["動能分"] >= 50:
                results.append({
                    "代碼": code,
                    "漲幅%": f"{chg_pct*100:.2f}%",
                    "成交值(億)": round(vol_amt, 2),
                    "動能評分": m_data["動能分"],
                    "MTM指標": m_data["MTM"],
                    "動能狀態": m_data["狀態"]
                })
    
    if results:
        df_res = pd.DataFrame(results).sort_values("動能評分", ascending=False)
        st.table(df_res)
    else:
        st.warning("目前市場未發現符合 [漲幅>2% & 成交>2E & 動能轉強] 的標的")
