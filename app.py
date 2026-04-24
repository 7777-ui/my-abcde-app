import streamlit as st
import yfinance as yf
import pandas as pd
import os
import re

# --- 1. 穩定的數據抓取與動能評分 (三竹 SDK 邏輯) ---
def get_stock_analysis(code):
    suffix = ".TW" if len(code) <= 4 else ".TWO"
    ticker = yf.Ticker(f"{code}{suffix}")
    
    # 抓取歷史數據 (計算 MTM 與 MA)
    df = ticker.history(period="1mo")
    if df.empty or len(df) < 15:
        return None

    # A. 基礎即時數據 (來自 yfinance 內部 fast_info)
    try:
        p_curr = df['Close'].iloc[-1]
        p_yest = df['Close'].iloc[-2]
        # 成交值計算 (當日成交量 * 當日收盤價 / 1億)
        # yfinance 的 Volume 單位是股
        vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
        chg_pct = (p_curr - p_yest) / p_yest
    except:
        return None

    # B. 2E 准入與漲幅 2% 門檻檢查
    # 如果要測試，可以先把門檻調低 (如 vol_amt >= 0.1) 看看有沒有跑出東西
    if vol_amt < 2.0 or chg_pct < 0.02:
        return None

    # C. 三竹動能參數計算 (Day=10, MA=10)
    prices = df['Close'].tolist()
    
    # 計算 MTM 序列 (當前 - 10日前)
    mtm_series = []
    for i in range(10, len(prices)):
        mtm_series.append(prices[i] - prices[i-10])
    
    curr_mtm = mtm_series[-1]
    mtm_ma = sum(mtm_series[-10:]) / 10
    
    # D. 加權分數系統 (模仿三竹動能欄位)
    # 1. 站上均線 (MTM > MTM_MA) +50分
    # 2. 正向動能 (MTM > 0) +20分
    # 3. 乖離強度 (加權加分，最高30分)
    score = 0
    if curr_mtm > mtm_ma: score += 50
    if curr_mtm > 0: score += 20
    
    strength_gap = (curr_mtm - mtm_ma) / (abs(mtm_ma) if mtm_ma != 0 else 1)
    score += min(30, max(0, strength_gap * 100))
    
    return {
        "代碼": code,
        "現價": round(p_curr, 2),
        "漲幅%": f"{chg_pct*100:.2f}%",
        "成交值(億)": round(vol_amt, 2),
        "動能分": int(score),
        "MTM": round(curr_mtm, 2),
        "MTM_MA": round(mtm_ma, 2),
        "狀態": "🚀強勁" if score >= 80 else "🟢轉強"
    }

# --- 2. 側邊欄與 CSV 讀取 ---
st.set_page_config(page_title="動能參數校準", layout="wide")
st.title("🏹 三竹 SDK 動能加權測試")

@st.cache_data
def load_codes():
    all_codes = []
    for f in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f):
            df = pd.read_csv(f, encoding='utf-8-sig')
            codes = df.iloc[:, 0].astype(str).str.strip().tolist()
            all_codes.extend([c for c in codes if c.isdigit()])
    return list(set(all_codes))

# --- 3. 執行邏輯 ---
if st.sidebar.button("📡 啟動全市場一鍵掃描"):
    codes = load_codes()
    if not codes:
        # 如果沒 CSV，給幾檔熱門股測試
        codes = ["2330", "2317", "1513", "2363", "3231", "2382", "2603", "2609"]
        st.warning("未偵測到 CSV，使用熱門股進行測試。")
        
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, c in enumerate(codes):
        if i % 5 == 0:
            status_text.text(f"掃描中: {c} ({i}/{len(codes)})")
            progress_bar.progress((i+1)/len(codes))
            
        data = get_stock_analysis(c)
        if data:
            results.append(data)
            
    progress_bar.empty()
    status_text.empty()
    
    if results:
        res_df = pd.DataFrame(results).sort_values("動能分", ascending=False)
        st.subheader(f"✅ 符合條件標的 (共 {len(res_df)} 檔)")
        st.dataframe(res_df, use_container_width=True, hide_index=True)
    else:
        st.error("❌ 掃描完成：沒有任何個股同時符合 [漲幅>2%、成交值>2E、MTM>MA] 之條件。")
