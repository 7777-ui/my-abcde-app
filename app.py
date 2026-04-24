import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 三竹動能核心邏輯 (嚴格對齊 SDK) ---
def calculate_mtm_sdk(df, p_curr):
    """
    Day=10, MA=10
    Precision=2, Tick_Type=Day
    """
    if df is None or len(df) < 22:
        return 0, 0, False, 0
    
    # 建立包含即時價的序列
    # yfinance 下載的 Close 可能包含今天，也可能只到昨天
    prices = df['Close'].dropna().tolist()
    if len(prices) > 25:
        prices = prices[-25:] # 取最近 25 天即可
    
    # 確保最後一筆是最新價
    prices.append(p_curr)
    
    # 計算 MTM 序列 (現在 - 10天前)
    mtms = []
    for i in range(10, len(prices)):
        mtms.append(prices[i] - prices[i-10])
    
    if len(mtms) < 10: return 0, 0, False, 0
    
    curr_mtm = round(mtms[-1], 2)
    mtm_ma10 = round(sum(mtms[-10:]) / 10, 2)
    
    # PROC (變動率)
    p_ref = prices[-11] # 10天前的價格
    proc = round((curr_mtm / p_ref) * 100, 2) if p_ref != 0 else 0
    
    # 動能強弱判定：三竹標準通常是 MTM > 0
    # 轉強判定：MTM > MTM_MA
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma10
    
    return curr_mtm, proc, is_strong, mtm_ma10

# --- 1. 穩定版即時價格抓取 ---
def get_price_stable(code):
    try:
        url = f"https://tw.stock.yahoo.com/quote/{code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        resp = requests.get(url, headers=headers, timeout=3)
        m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', resp.text)
        if m: return float(m.group(1))
    except: pass
    return None

# --- 2. 核心掃描器 ---
def run_power_scan(codes, is_auto=False):
    results = []
    # 修正進度條顯示
    prog_bar = st.progress(0)
    status_text = st.empty()
    
    count = 0
    total = len(codes)

    for code in codes:
        count += 1
        if count % 10 == 0: # 每 10 檔更新一次進度，減少介面閃爍
            prog_bar.progress(count / total)
            status_text.text(f"📡 雷達掃描中: {code} ({count}/{total})")

        # 抓取數據 (強制關閉多執行緒提升穩定性)
        ticker = f"{code}.TW"
        df = yf.download(ticker, period="1mo", interval="1d", progress=False, threads=False)
        if df.empty:
            ticker = f"{code}.TWO"
            df = yf.download(ticker, period="1mo", interval="1d", progress=False, threads=False)
        
        if df.empty: continue
        
        # 取得價格與成交量
        p_yest = float(df['Close'].iloc[-1])
        p_curr = get_price_stable(code)
        if not p_curr: p_curr = p_yest
        
        chg = (p_curr - p_yest) / p_yest
        vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
        
        # --- 4/24 實測調整門檻 ---
        # 如果要對齊三竹 70 檔，門檻不能設太高
        if is_auto:
            if chg < 0.01: continue # 漲幅至少要 1%
            if vol_amt < 0.5: continue # 成交值降到 0.5 億 (避免漏掉中小型動能股)

        # 計算三竹動能
        mtm, proc, is_strong, mtm_ma = calculate_mtm_sdk(df, p_curr)
        
        # 只要符合 MTM > 0 (價漲動能基礎) 就顯示
        if mtm > 0:
            # 這裡之後可以串接你的姊布林 ABCDE 邏輯
            res_tag = "🚀 動能轉強" if is_strong else "⚪ 持續動能"
            
            results.append({
                "代號": code,
                "名稱": stock_info_map.get(code, {}).get("簡稱", "未知"),
                "策略": res_tag,
                "動能(PROC%)": proc,
                "MTM值": mtm,
                "現價": p_curr,
                "漲幅%": f"{chg*100:.2f}%",
                "成交值(億)": round(vol_amt, 2),
                "MTM均線": mtm_ma
            })

    prog_bar.empty()
    status_text.empty()
    return results

# --- 3. 介面與執行 ---
st.title("🏹 姊布林 x 三竹動能雷達")

# 假設 stock_info_map 已在外部讀取 CSV 完畢
if st.sidebar.button("📡 啟動全市場掃描 (對齊三竹)"):
    if not stock_info_map:
        st.error("❌ 找不到 CSV 股票清單，請確認檔案路徑。")
    else:
        all_codes = list(stock_info_map.keys())
        final_list = run_power_scan(all_codes, is_auto=True)
        
        if final_list:
            st.session_state.scan_results = pd.DataFrame(final_list)
            st.success(f"✅ 掃描完成！共找到 {len(final_list)} 檔動能標的。")
        else:
            st.warning("查無標的。請確認網路連線或稍後再試。")

if "scan_results" in st.session_state:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
