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

# --- 0. 🚀 即時數據抓取函數 (Yahoo Finance 爬蟲) ---
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

# --- 0.1 🏎️ 歷史數據與動能計算 (對齊三竹 SDK: Day=10, MA=10) ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="3mo", progress=False)

def calculate_momentum_sdk(df, p_curr):
    """計算三竹動能 MTM(10) 與 MTM 均線"""
    if df is None or len(df) < 25: return 0, 0, False
    # 取得歷史收盤價序列
    prices = df['Close'].dropna().tolist()
    # 將即時價格加入序列末端
    full_prices = prices + [p_curr]
    
    # MTM(10): 當前價 - 10日前價
    mtm_series = []
    for i in range(10, len(full_prices)):
        mtm_series.append(full_prices[i] - full_prices[i-10])
    
    curr_mtm = round(mtm_series[-1], 2)
    mtm_ma10 = sum(mtm_series[-10:]) / 10
    
    # 轉強條件：MTM > 0 且 站在 MTM 均線之上
    is_strong = curr_mtm > 0 and curr_mtm > mtm_ma10
    
    # PROC% (10日變動率)
    p_ref = full_prices[-11]
    proc = round((curr_mtm / p_ref) * 100, 2) if p_ref != 0 else 0
    
    return curr_mtm, proc, is_strong

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; padding: 5px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 3. 🛡️ 族群 CSV 讀取 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    files = ["TWSE.csv", "TPEX.csv"] 
    for f_name in files:
        if os.path.exists(f_name):
            try:
                try: df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df_local = pd.read_csv(f_name, encoding='cp950')
                df_local = df_local.fillna('-')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    rt_indices = {"上市": "TSE", "上櫃": "OTC"}
    yf_indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in rt_indices.items():
        try:
            curr_p = get_realtime_price(v)
            df_h = get_historical_data(yf_indices[k])
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                base_list = df_h['Close'].iloc[-19:].tolist()
                c_list = base_list + [curr_p]
                m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
                std_v = pd.Series(c_list).std()
                bw = (std_v * 4) / m20 if m20 != 0 else 0.0
                light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
            else: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
        except: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
    return res

m_env = get_market_env()

# --- 5. 核心分析處理 (整合 ABCDE 與 三竹動能) ---
def analyze_stocks(codes, filter_mode=False):
    results = []
    main_market_light = m_env['上市']['燈號']
    
    for code in codes:
        info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
        p_curr = get_realtime_price(code)
        if not p_curr: continue
        
        # 抓取數據與判定市場
        df = get_historical_data(f"{code}.TW")
        m_type = "上市"
        if df.empty or len(df) < 20:
            df = get_historical_data(f"{code}.TWO")
            m_type = "上櫃"
        if df.empty or len(df) < 20: continue
        
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        df = df.dropna(subset=['Close'])
        
        # 1. 基礎指標計算
        p_yest = float(df['Close'].iloc[-1])
        chg = (p_curr - p_yest) / p_yest
        # 🔥 成交值修正 (張數 * 價格 * 1000 / 1億)
        vol_amt = (df['Volume'].iloc[-1] * p_curr * 1000) / 100000000 
        
        # 2. 三竹動能 SDK 計算 (Day=10, MA=10)
        mtm_val, proc_val, is_strong = calculate_momentum_sdk(df, p_curr)
        
        # --- 全市場掃描過濾門檻 ---
        if filter_mode:
            if chg < 0.02: continue      # 漲幅 > 2%
            if vol_amt < 2.0: continue   # 成交值 > 2 億
            if not is_strong: continue   # 動能轉強
            
        # 3. 姊布林 ABCDE 邏輯
        current_env = m_env[m_type]
        history_for_ma = df['Close'].iloc[-19:].tolist()
        close_20 = history_for_ma + [p_curr]
        m20_now = sum(close_20) / 20
        std_now = pd.Series(close_20).std()
        upper_now = m20_now + (std_now * 2)
        bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
        ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
        slope_pos = m20_now > sum(history_for_ma) / 20
        
        res_tag = ""
        if p_curr > upper_now and slope_pos and vol_amt >= 5:
            # (此處省略部分詳細 ABCDE 判斷邏輯，維持與原程式碼一致)
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
            "代號": code, "名稱": info["簡稱"], 
            "動能": "🚀轉強" if is_strong else "⚪平穩",
            "ABCDE策略": res_tag if res_tag else "⚪觀察",
            "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
            "MTM": mtm_val, "PROC%": proc_val, "個股帶寬%": f"{bw*100:.1f}%",
            "族群細分": info["族群細分"], "關鍵技術": info["關鍵技術"]
        })
    return results

# --- 6. 主畫面顯示 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室 (三竹動能同步版)")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 7. 側邊欄控制區 ---
st.sidebar.title("🛠️ 戰情控制中心")
raw_input = st.sidebar.text_area("1. 手動輸入代碼 (不限門檻)", height=100)
if st.sidebar.button("🔍 執行指定搜尋"):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    if codes:
        st.session_state.scan_results = pd.DataFrame(analyze_stocks(codes, filter_mode=False))

st.sidebar.markdown("---")
if st.sidebar.button("📡 啟動全市場動能掃描"):
    all_codes = list(stock_info_map.keys())
    with st.spinner(f"正在分析全台股 {len(all_codes)} 檔標的..."):
        res = analyze_stocks(all_codes, filter_mode=True)
        if res:
            st.session_state.scan_results = pd.DataFrame(res)
            st.sidebar.success(f"找到 {len(res)} 檔符合動能標的！")
        else:
            st.sidebar.warning("當前無標的符合「漲>2%且量>2億」及「動能轉強」條件。")

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()

# --- 8. 結果數據表 ---
if st.session_state.scan_results is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
