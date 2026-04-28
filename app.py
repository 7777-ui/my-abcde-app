import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 0. 🚀 核心抓取函數 ---
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

@st.cache_data(ttl=86400)
def get_monthly_revenue(year, month):
    """自動抓取公開資訊觀測站營收彙整表"""
    url = f"https://mops.twse.com.tw/nas/t110/stock/t110sc17_{year}_{month}_0.html"
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'cp950'
        dfs = pd.read_html(io.StringIO(response.text))
        combined_df = pd.concat([df for df in dfs if "公司代號" in df.columns])
        combined_df.columns = [str(c[1]) if isinstance(c, tuple) else str(c) for c in combined_df.columns]
        return combined_df[['公司代號', '公司名稱', '去年同月增減(%)']]
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 1. 介面設定 ---
st.set_page_config(page_title="🏹 策略戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

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

# --- 3. CSV 讀取 ---
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
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業排位": str(row.iloc[2]).strip(), "實力指標": str(row.iloc[3]).strip(), "族群細分": str(row.iloc[4]).strip(), "關鍵技術": str(row.iloc[5]).strip()}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 側邊欄與導覽 ---
st.sidebar.title("🛠️ 戰情總部")
mode = st.sidebar.radio("請選擇分析策略", ["🏹 姊布林 ABCDE", "📊 營收動能 (年增>20%)"])

# --- 5. 策略邏輯區 ---

# ---- 策略 A: 姊布林 ABCDE ----
if mode == "🏹 姊布林 ABCDE":
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
                    base_list = df_h['Close'].iloc[-20:-1].tolist() if df_h.index[-1].date() >= datetime.now().date() else df_h['Close'].iloc[-19:].tolist()
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
    st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
    m_col1, m_col2 = st.columns(2)
    with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['
