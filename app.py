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

# --- 0. 🚀 即時數據與動能計算核心 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
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
    return yf.download(code_with_suffix, period="3mo", progress=False)

def calculate_mtm_logic(df, p_curr):
    """實作三竹 SDK 動能邏輯: Day=10, MA=10"""
    if len(df) < 25: return 0, 0, False
    prices = df['Close'].tolist()[:-1] + [p_curr]
    # MTM = 當前價 - 10日前價
    mtm_series = []
    for i in range(10, len(prices)):
        mtm_series.append(prices[i] - prices[i-10])
    
    current_mtm = mtm_series[-1]
    mtm_ma10 = sum(mtm_series[-10:]) / 10
    proc = (current_mtm / prices[-11]) * 100 if prices[-11] != 0 else 0
    
    # 動能轉強判定：MTM線 由下往上穿過 MTM均線 或 維持在均線上
    is_momentum_strong = current_mtm > mtm_ma10 and current_mtm > 0
    return round(current_mtm, 2), round(proc, 2), is_momentum_strong

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# 背景設置函數 (簡略版)
def set_ui_cleanup(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""<style>.stApp {{ background-image: url("data:image/jpeg;base64,{b64}"); background-size: cover; }} .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: -1; }}</style>""", unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False
if not st.session_state.password_correct:
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 3. 數據與環境 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                df = pd.read_csv(f_name, encoding='utf-8-sig')
            except:
                df = pd.read_csv(f_name, encoding='cp950')
            for _, row in df.iterrows():
                code = str(row.iloc[0]).strip()
                if code.isdigit():
                    mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業": str(row.iloc[2]).strip()}
    return mapping

stock_info_map = get_stock_info_full()

@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    for k, v, yf_k in [("上市", "TSE", "^TWII"), ("上櫃", "OTC", "^TWOII")]:
        curr_p = get_realtime_price(v)
        df_h = get_historical_data(yf_k)
        if not df_h.empty and curr_p:
            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
            c_list = df_h['Close'].iloc[-19:].tolist() + [curr_p]
            m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
            std = pd.Series(c_list).std()
            bw = (std * 4) / m20 if m20 != 0 else 0
            light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
    return res

m_env = get_market_env()

# --- 4. 顯示儀表板 ---
st.markdown("### 🏹 姊布林 ABCDE 戰情室 (三竹動能一鍵掃描版)")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 5. 核心掃描邏輯 ---
def process_scanning(codes, is_auto=False):
    results = []
    main_market_light = m_env['上市']['燈號']
    with st.spinner("雷達掃描中..."):
        for code in codes:
            p_curr = get_realtime_price(code)
            if not p_curr: continue
            
            df = get_historical_data(f"{code}.TW")
            m_type = "上市"
            if df.empty or len(df) < 20:
                df = get_historical_data(f"{code}.TWO")
                m_type = "上櫃"
            
            if df.empty: continue
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            # A. 三竹動能判定
            mtm, proc, is_strong = calculate_mtm_logic(df, p_curr)
            
            # 如果是自動掃描，只顯示動能轉強(is_strong)的
            if is_auto and not is_strong: continue
            
            # B. 姊布林策略計算
            info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業": "-"})
            p_yest = float(df['Close'].iloc[-1])
            chg = (p_curr - p_yest) / p_yest
            history_20 = df['Close'].iloc[-19:].tolist() + [p_curr]
            m20 = sum(history_20) / 20
            std = pd.Series(history_20).std()
            upper = m20 + (std * 2)
            bw = (std * 4) / m20 if m20 != 0 else 0
            vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
            
            res_tag = ""
            current_env = m_env[m_type]
            ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
            slope_pos = m20 > sum(df['Close'].iloc[-20:-1]) / 20
            
            # 策略判定邏輯 (同前次修正)
            if p_curr > upper and slope_pos and vol_amt >= 5:
                if "🔴 紅燈" in main_market_light:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                else:
                    if "🟢 綠燈" in current_env['燈號']:
                        env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                        if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：共振】"
                        elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額】"
                        elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                    elif "🟡 黃燈" in current_env['燈號']:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
            
            results.append({
                "代號": code, "名稱": info["簡稱"], "動能(PROC%)": f"{proc:.2f}%",
                "策略": res_tag if res_tag else "⚪ 未達標",
                "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                "個股帶寬%": f"{bw*100:.2f}%", "產業": info["產業"]
            })
    return results

# --- 6. 側邊欄控制 ---
st.sidebar.title("🛠️ 戰情設定")
raw_input = st.sidebar.text_area("1. 手動輸入股號", height=100)
if st.sidebar.button("🚀 開始掃描手動清單"):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    if codes:
        st.session_state.scan_results = pd.DataFrame(process_scanning(codes))

st.sidebar.markdown("---")
if st.sidebar.button("📡 啟動全市場動能雷達"):
    all_codes = list(stock_info_map.keys())
    # 這裡會跑比較久，建議實際運作時可限制成交量
    res = process_scanning(all_codes, is_auto=True)
    if res:
        st.session_state.scan_results = pd.DataFrame(res)

# --- 7. 結果顯示 ---
if st.session_state.scan_results is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
