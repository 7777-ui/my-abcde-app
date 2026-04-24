import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 數據修復與動能計算 ---
def fix_yf_df(df):
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=['Close'])

def calculate_mtm_sdk(df, p_curr):
    """三竹參數: Day=10, MA=10"""
    if len(df) < 22: return 0, 0, False
    prices = df['Close'].tolist() + [p_curr]
    mtm_series = [prices[i] - prices[i-10] for i in range(10, len(prices))]
    curr_mtm = round(mtm_series[-1], 2)
    mtm_ma = sum(mtm_series[-10:]) / 10
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma
    proc = round((curr_mtm / prices[-11]) * 100, 2) if prices[-11] != 0 else 0
    return curr_mtm, proc, is_strong

def get_realtime_price(stock_id):
    url = f"https://tw.stock.yahoo.com/quote/{stock_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=5)
        m = re.search(r'"regularMarketPrice":\s*([0-9.]+)', resp.text)
        if m: return float(m.group(1).replace(',', ''))
    except: pass
    return None

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林戰情室", layout="wide")
st_autorefresh(interval=180000, key="refresh")

# --- 2. 🛡️ CSV 讀取 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                df_local = pd.read_csv(f_name, encoding='utf-8-sig').fillna('-')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    mapping[code] = {
                        "簡稱": str(row.iloc[1]).strip(),
                        "族群": str(row.iloc[4]).strip() if len(row)>4 else "-",
                        "實力指標": str(row.iloc[3]).strip() if len(row)>3 else "-",
                        "關鍵技術": str(row.iloc[5]).strip() if len(row)>5 else "-"
                    }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 3. 核心分析引擎 ---
def run_analytics(codes, is_global_scan=False):
    results = []
    # 模擬大盤帶寬 (此處可根據實際大盤狀況調整)
    mkt_bw_tse = 0.15 
    mkt_bw_otc = 0.10
    
    progress = st.progress(0)
    for idx, code in enumerate(codes):
        progress.progress((idx + 1) / len(codes))
        p_curr = get_realtime_price(code)
        if not p_curr: continue
        
        df = yf.download(f"{code}.TW", period="3mo", progress=False)
        if df.empty: df = yf.download(f"{code}.TWO", period="3mo", progress=False)
        if df.empty: continue
        df = fix_yf_df(df)
        if len(df) < 22: continue
        
        # --- A. 基礎指標 ---
        p_yest = float(df['Close'].iloc[-1])
        chg = (p_curr - p_yest) / p_yest
        vol_amt = (df['Volume'].iloc[-1] * p_curr * 1000) / 100000000 
        mtm, proc, is_strong = calculate_mtm_sdk(df, p_curr)
        
        # --- B. 准入門檻過濾 (2E 門檻) ---
        # 如果是全市場掃描，沒過 2E 或沒漲或動能沒轉強，就不顯示
        if is_global_scan:
            if vol_amt < 2.0 or chg <= 0 or not is_strong: continue

        # --- C. 姊布林 ABCDE 策略判定 (5E 門檻 + 其他參數) ---
        history_20 = df['Close'].iloc[-19:].tolist() + [p_curr]
        ma20 = sum(history_20) / 20
        std = pd.Series(history_20).std()
        upper = ma20 + (std * 2)
        bw = (std * 4) / ma20 if ma20 != 0 else 0
        slope_pos = ma20 > (sum(df['Close'].iloc[-20:-1]) / 20)
        
        # 決定個股比值 (假設預設)
        ratio = bw / mkt_bw_otc 
        
        # 邏輯診斷
        fail_reasons = []
        if vol_amt < 5.0: fail_reasons.append("量不足5E")
        if p_curr <= upper: fail_reasons.append("未站上軌")
        if not slope_pos: fail_reasons.append("斜率負")
        
        strategy_tag = ""
        if not fail_reasons:
            # 符合所有基礎條件，進入級別判定
            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: strategy_tag = "🔥【A：潛龍】"
            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: strategy_tag = "🎯【B：海龍】"
            elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: strategy_tag = "🌊【C：瘋狗】"
            elif bw > 0.2 and 0.8 <= ratio <= 1.2: strategy_tag = "💎【D：共振】"
            elif bw > 0.2 and 1.2 < ratio <= 2.0: strategy_tag = "🚀【E：超額】"
            else: strategy_tag = "⚪ 參數不符(ABCDE)"
        else:
            strategy_tag = "⚪ " + "/".join(fail_reasons)

        info = stock_info_map.get(code, {"簡稱": "台股", "族群": "-", "實力指標": "-", "關鍵技術": "-"})
        results.append({
            "代號": code,
            "名稱": info["簡稱"],
            "動能": "🚀 轉強" if is_strong else "⚪ 平穩",
            "策略標籤": strategy_tag,
            "現價": p_curr,
            "漲幅%": f"{chg*100:.2f}%",
            "成交值(億)": round(vol_amt, 2),
            "MTM": mtm,
            "PROC%": proc,
            "個股帶寬%": f"{bw*100:.1f}%",
            "族群": info["族群"],
            "2026指標": info["實力指標"]
        })
    progress.empty()
    return results

# --- 4. 介面 ---
st.title("🏹 姊布林 ABCDE 戰情室")
st.info("💡 准入門檻：成交值 > 2E 且動能轉強即顯示 | 策略標籤：成交值需 > 5E 且符合走勢參數")

st.sidebar.header("🛠️ 戰情控制中心")
raw_input = st.sidebar.text_area("1. 手動代碼搜尋", placeholder="2330 2317")
if st.sidebar.button("🔍 執行指定搜尋"):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    if codes:
        st.session_state.scan_results = pd.DataFrame(run_analytics(codes, False))

st.sidebar.markdown("---")
if st.sidebar.button("📡 全市場動能掃描 (2E)"):
    all_codes = list(stock_info_map.keys())
    with st.spinner("正在分析全台股動能..."):
        res = run_analytics(all_codes, True)
        if res:
            st.session_state.scan_results = pd.DataFrame(res)
        else:
            st.sidebar.warning("目前市場無符合 2E 且動能轉強標的")

# --- 5. 數據顯示 ---
if "scan_results" in st.session_state and st.session_state.scan_results is not None:
    st.subheader(f"📊 實時戰情表 (共 {len(st.session_state.scan_results)} 檔滿足 2E 准入)")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
