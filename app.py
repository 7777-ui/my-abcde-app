import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64

# --- 1. 網頁配置與 UI 強力隱藏 (解決問題 2) ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

def set_final_clean_ui(image_file):
    # 讀取背景圖
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    
    style = f"""
    <style>
    /* 隱藏背景與設定透明度 */
    .stApp {{
        background-image: url("data:image/png;base64,{b64_encoded}");
        background-attachment: fixed;
        background-size: cover;
    }}
    .stApp::before {{
        content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
        background-color: rgba(0, 0, 0, 0.7); z-index: -1;
    }}

    /* 🔴 強力隱藏右下角 Manage app 按鈕與所有選單 (針對問題 2) */
    [data-testid="manage-app-button"], 
    .stManageAppButton, 
    #MainMenu, 
    header, 
    footer, 
    iframe[title="Manage app"] {{
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
    }}
    
    /* 調整表格字體與寬度 */
    .stDataFrame {{ width: 100%; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)

set_final_clean_ui("header_image.jpg")

# --- 2. 🛡️ 台股名稱校正功能 (解決問題 1) ---
@st.cache_data(ttl=86400)
def get_tw_stock_names():
    mapping = {}
    try:
        # 同步抓取上市與上櫃官方清單
        for mode in ["2", "4"]:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
            r = requests.get(url, timeout=10)
            df = pd.read_html(r.text)[0]
            for val in df.iloc[:, 0]:
                parts = str(val).split('\u3000') # 使用全形空格分割
                if len(parts) >= 2:
                    mapping[parts[0].strip()] = parts[1].strip()
    except: pass
    return mapping

stock_db = get_tw_stock_names()

# --- 3. 核心燈號與大盤帶寬判定 ---
@st.cache_data(ttl=300)
def get_market_status():
    status = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for label, ticker in indices.items():
        df = yf.download(ticker, period="2mo", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        
        close = df['Close'].iloc[-1]
        ma5 = df['Close'].rolling(5).mean().iloc[-1]
        ma20 = df['Close'].rolling(20).mean().iloc[-1]
        std20 = df['Close'].rolling(20).std().iloc[-1]
        bandwidth = (std20 * 4) / ma20
        
        # 🟢綠燈: 指數 > 5MA | 🟡黃燈: 5MA > 指數 > 20MA | 🔴紅燈: 指數 < 20MA
        if close > ma5: light = "🟢 綠燈"
        elif close > ma20: light = "🟡 黃燈"
        else: light = "🔴 紅燈"
        
        status[label] = {"燈號": light, "帶寬": bandwidth, "現價": close}
    return status

m_status = get_market_status()

# --- 4. 戰情室介面 ---
st.title("🏹 姊布林 ABCDE 策略戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_status['上市']['現價']:,.2f})", m_status['上市']['燈號'], f"帶寬: {m_status['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_status['上櫃']['現價']:,.2f})", m_status['上櫃']['燈號'], f"帶寬: {m_status['上櫃']['帶寬']:.2%}")

# --- 5. 策略判定核心 (吻合 ABCDE 準則) ---
raw_input = st.sidebar.text_area("請輸入股票代碼", height=200)
if st.sidebar.button("開始掃描戰情"):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    final_list = []
    
    for code in codes:
        # 下載個股資料
        df = yf.download(f"{code}.TW", period="3mo", progress=False)
        market_type = "上市"
        if df.empty or len(df) < 20:
            df = yf.download(f"{code}.TWO", period="3mo", progress=False)
            market_type = "上櫃"
            
        if not df.empty and len(df) >= 20:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            # 1. 計算基礎指標
            df['20MA'] = df['Close'].rolling(20).mean()
            df['Upper'] = df['20MA'] + (df['Close'].rolling(20).std() * 2)
            
            p_curr = df['Close'].iloc[-1]
            p_yest = df['Close'].iloc[-2]
            chg = (p_curr - p_yest) / p_yest
            bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / df['20MA'].iloc[-1]
            vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000 # 億
            slope_pos = df['20MA'].iloc[-1] > df['20MA'].iloc[-2] # 20MA上揚
            ratio = bw / m_status[market_type]['帶寬']
            
            # 2. 核心通用濾網：突破上軌 + 20MA上揚 + 成交值 > 5億
            is_breakout = (p_curr > df['Upper'].iloc[-1]) and slope_pos and (vol_amt >= 5)
            
            res = "⚪ 未達准入"
            current_light = m_status[market_type]['燈號']
            
            if is_breakout:
                # 判定 D/E 環境條件
                env_de = (m_status['上市']['帶寬'] > 0.145 or m_status['上櫃']['帶寬'] > 0.095)
                
                # 🟢 綠燈：全系列開啟
                if "🟢" in current_light:
                    if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res = "💎【D：帶寬共振】"
                    elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res = "🚀【E：超額擴張】"
                    elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res = "🔥【A：潛龍爆發】"
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res = "🎯【B：海龍狙擊】"
                    elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res = "🌊【C：瘋狗浪】"
                
                # 🟡 黃燈：僅限 A, B
                elif "🟡" in current_light:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res = "🔥【A：潛龍爆發】"
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res = "🎯【B：海龍狙擊】"
                
                # 🔴 紅燈：僅限 A
                elif "🔴" in current_light:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res = "🔥【A：潛龍爆發】"

            final_list.append({
                "代碼": code, 
                "台股名稱": stock_db.get(code, "未知"), 
                "判定結果": res, 
                "個股帶寬%": f"{bw:.2%}", 
                "今日漲幅%": f"{chg:.2%}", 
                "成交值(億)": f"{vol_amt:.1f}"
            })

    if final_list:
        st.table(pd.DataFrame(final_list))
