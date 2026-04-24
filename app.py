import streamlit as st
import yfinance as yf
import pandas as pd
import os

# --- 1. 核心計算：三竹動能加權分 ---
def get_stock_analysis(code):
    suffix = ".TW" if len(code) <= 4 else ".TWO"
    # 使用 period="1mo" 確保有足夠的 10 日區間計算 MTM MA
    ticker = yf.Ticker(f"{code}{suffix}")
    df = ticker.history(period="1mo")
    
    if df.empty or len(df) < 15:
        return None

    try:
        # yf 下載的 Close 是價格，Volume 是股數
        p_curr = df['Close'].iloc[-1]
        p_yest = df['Close'].iloc[-2]
        # 成交值 (億) = (股數 * 價格) / 1億
        vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
        chg_pct = (p_curr - p_yest) / p_yest
        
        # --- 門檻檢查：2億 + 漲幅2% ---
        # 如果要進行「一定跑得出結果」的測試，請將 2.0 改為 0.1
        if vol_amt < 2.0 or chg_pct < 0.02:
            return None

        # --- 三竹 MTM (10, 10) 邏輯 ---
        prices = df['Close'].tolist()
        mtm_series = [prices[i] - prices[i-10] for i in range(10, len(prices))]
        
        curr_mtm = mtm_series[-1]
        mtm_ma = sum(mtm_series[-10:]) / 10
        
        # --- 動能評分 (加權分數) ---
        score = 0
        if curr_mtm > mtm_ma: score += 50  # 穿過均線
        if curr_mtm > 0: score += 20      # 正向動能
        
        # 乖離加權 (強度)
        diff = (curr_mtm - mtm_ma) / (abs(mtm_ma) if mtm_ma != 0 else 1)
        score += min(30, max(0, diff * 100))
        
        return {
            "代碼": code,
            "現價": round(p_curr, 2),
            "漲幅%": f"{chg_pct*100:.2f}%",
            "成交值(億)": round(vol_amt, 2),
            "動能分": int(score),
            "狀態": "🚀強勁" if score >= 80 else "🟢轉強"
        }
    except:
        return None

# --- 2. 修正後的 CSV 讀取 (解決 UnicodeDecodeError) ---
@st.cache_data
def load_codes():
    all_codes = []
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            # 嘗試三種常見編碼，直到不報錯為止
            for enc in ['utf-8-sig', 'cp950', 'big5']:
                try:
                    df = pd.read_csv(f_name, encoding=enc)
                    codes = df.iloc[:, 0].astype(str).str.strip().tolist()
                    all_codes.extend([c for c in codes if c.isdigit()])
                    break # 成功讀取就跳出編碼嘗試
                except:
                    continue
    return list(set(all_codes))

# --- 3. 介面與掃描邏輯 ---
st.set_page_config(page_title="動能參數校準", layout="wide")
st.title("🏹 三竹 SDK 動能加權測試")

# 初始化 Session State 避免第二張圖的 TypeError
if "results_df" not in st.session_state:
    st.session_state.results_df = None

if st.sidebar.button("📡 啟動全市場一鍵掃描"):
    codes = load_codes()
    if not codes:
        st.error("❌ 無法讀取 CSV 檔案，請確認檔案編碼或是否存在。")
    else:
        found_data = []
        bar = st.progress(0)
        status = st.empty()
        
        for i, c in enumerate(codes):
            if i % 10 == 0:
                status.text(f"掃描中: {c} ({i}/{len(codes)})")
                bar.progress((i+1)/len(codes))
            
            res = get_stock_analysis(c)
            if res:
                found_data.append(res)
        
        bar.empty()
        status.empty()
        
        if found_data:
            st.session_state.results_df = pd.DataFrame(found_data).sort_values("動能分", ascending=False)
        else:
            st.session_state.results_df = "EMPTY"

# --- 4. 顯示結果 (增加防呆檢查) ---
if st.session_state.results_df is not None:
    if isinstance(st.session_state.results_df, pd.DataFrame):
        st.subheader(f"✅ 發現 {len(st.session_state.results_df)} 檔符合條件標的")
        st.dataframe(st.session_state.results_df, use_container_width=True, hide_index=True)
    elif st.session_state.results_df == "EMPTY":
        st.warning("⚠️ 掃描完成，但目前沒有股票同時符合 [漲幅>2% & 成交>2億 & 動能轉強]。")
else:
    st.info("💡 請點擊左側「啟動全市場一鍵掃描」按鈕。")
