import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64
import pytz

# [2026/04/04 02:22:10] 網頁配置與隱藏所有平台雜訊
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    [data-testid="manage-app-button"], .stManageAppButton, iframe[title="Manage app"], footer, header, #MainMenu {{ display: none !important; }}
    div[data-testid="stHorizontalBlock"] {{ position: sticky; top: 0px; z-index: 1000; background-color: rgba(30, 30, 30, 0.6); padding: 15px; border-radius: 12px; backdrop-filter: blur(10px); }}
    .stDataFrame, .stTable {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; }}
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

# --- 3. 🛡️ 官方台股名稱抓取 (修正：更強韌的抓取邏輯) ---
@st.cache_data(ttl=86400)
def get_tw_official_names():
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)'}
    try:
        for mode in ["2", "4"]:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
            r = requests.get(url, headers=headers, timeout=15)
            r.encoding = 'MS950'
            dfs = pd.read_html(r.text)
            df = dfs[0]
            for item in df.iloc[:, 0]:
                parts = str(item).split('\u3000') 
                if len(parts) >= 2:
                    mapping[parts[0].strip()] = parts[1].strip()
    except: pass
    return mapping

stock_name_map = get_tw_official_names()

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=300)
def get_market_env():
    res = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in indices.items():
        try:
            df = yf.download(v, period="3mo", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            c = df['Close'].iloc[-1]
            m5 = df['Close'].rolling(5).mean().iloc[-1]
            m20 = df['Close'].rolling(20).mean().iloc[-1]
            bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / m20
            light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": float(c), "帶寬": float(bw)}
        except: res[k] = {"燈號": "⚠️", "價格": 0, "帶寬": 0}
    return res

m_env = get_market_env()

# --- 5. 主畫面與策略判定 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據掃描時間（台北）：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M')}**")

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請輸入股票代碼", height=250)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("策略分析中..."):
        for code in codes:
            # [2026/04/04 02:22:10] 優先級 1: 從證交所快取清單抓取
            official_name = stock_name_map.get(code)
            
            # 下載歷史數據
            df = yf.download(f"{code}.TW", period="3mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 20:
                df = yf.download(f"{code}.TWO", period="3mo", progress=False)
                m_type = "上櫃"
            
            # [2026/04/04 02:22:10] 優先級 2: 如果清單抓不到且 official_name 是空或標點
            if not official_name or len(re.sub(r'[^\u4e00-\u9fa5]+', '', official_name)) == 0:
                try:
                    # 改用快速的 Ticker 抓取，並強化正規表達式
                    tk = yf.Ticker(f"{code}.TW" if m_type == "上市" else f"{code}.TWO")
                    # 抓取 Ticker 中的名稱並只留下「中文字」
                    raw_n = tk.info.get('shortName', tk.info.get('longName', ''))
                    official_name = "".join(re.findall(r'[\u4e00-\u9fa5]+', raw_n))
                except: pass
            
            # [2026/04/04 02:22:10] 優先級 3: 最終保險（若依然抓不到則顯示 代碼）
            if not official_name:
                official_name = f"台股 {code}"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                env = m_env[m_type]
                df['20MA'] = df['Close'].rolling(20).mean()
                df['Upper'] = df['20MA'] + (df['Close'].rolling(20).std() * 2)
                p_curr, p_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / df['20MA'].iloc[-1]
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                slope_pos = df['20MA'].iloc[-1] > df['20MA'].iloc[-2]
                break_upper = p_curr > df['Upper'].iloc[-1]
                
                res_tag = "⚪ 未達准入"
                if break_upper and slope_pos and vol_amt >= 5:
                    env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    if "🟢" in env['燈號']:
                        if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：帶寬共振】"
                        elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額擴張】"
                        elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍爆發】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍狙擊】"
                        elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗浪】"
                    elif "🟡" in env['燈號']:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍爆發】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍狙擊】"
                    elif "🔴" in env['燈號']:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍爆發】"

                results.append({
                    "代碼": code, "台股名稱": official_name, "判定結果": res_tag, 
                    "個股帶寬%": f"{bw*100:.2f}%", "漲幅%": f"{chg*100:.2f}%", 
                    "成交值(億)": round(vol_amt, 1), "對比比值": round(ratio, 2)
                })
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
