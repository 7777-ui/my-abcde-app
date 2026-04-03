import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
import time
import os
import base64

# --- 1. 設置網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

# --- 2. 背景圖片函數 (針對直向圖片優化：寬度填滿、對齊底部) ---
def set_bg_fixed(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            img_data = f.read()
        b64_encoded = base64.b64encode(img_data).decode()
        style = f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{b64_encoded}");
            background-attachment: fixed;
            background-size: 100% auto; 
            background-position: center bottom; 
            background-repeat: no-repeat;
            background-color: #0E1117;
        }}
        .stApp::before {{
            content: "";
            position: absolute;
            top: 0; left: 0; width: 100%; height: 100%;
            background-color: rgba(0, 0, 0, 0.65); 
            z-index: -1;
        }}
        header {{ visibility: hidden; }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_bg_fixed("header_image.jpg")

# --- 3. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct: return True
    st.title("🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    return False

if not check_password(): st.stop()

# --- 4. 核心名稱抓取 ---
@st.cache_data
def get_stock_names():
    try:
        url = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"
        url_otc = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
        def fetch(u):
            r = requests.get(u)
            d = pd.read_html(r.text)[0]
            d.columns = d.iloc[0]
            d = d.iloc[1:]
            res = {}
            for v in d['有價證券代號及名稱']:
                p = str(v).split('\u3000')
                if len(p) >= 2: res[p[0]] = p[1]
            return res
        all_names = fetch(url)
        all_names.update(fetch(url_otc))
        return all_names
    except: return {}

stock_names = get_stock_names()

# --- 5. 大盤環境偵測 (嚴格遵照 5MA/20MA 邏輯) ---
def get_market_status():
    status = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for name, sym in indices.items():
        try:
            df = yf.download(sym, period="2mo", interval="1d", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            
            df['5MA'] = df['Close'].rolling(5).mean()
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            curr = df.iloc[-1]
            price, m5, m20, bw = float(curr['Close']), float(curr['5MA']), float(curr['20MA']), float(curr['BW'])
            
            # --- 燈號判定 ---
            if price > m5: light = "🟢 綠燈"
            elif price > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
            
            status[name] = {"燈號": light, "價格": price, "帶寬": bw}
        except: status[name] = {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0}
    return status

# --- 6. 介面顯示 ---
st.title("🏹 私密戰情室：姊布林ABCDE 策略判定")
m_env = get_market_status()

def draw_market_card(title, data):
    p_str = f"{data['價格']:,.2f}" if data['價格'] > 0 else "---"
    bw_str = f"{data['帶寬']:.2%}"
    st.markdown(f"""
        <div style="background-color: rgba(30, 30, 30, 0.75); padding: 25px; border-radius: 12px; border-left: 6px solid #4CAF50; margin-bottom: 25px;">
            <p style="color: #AAAAAA; font-size: 24px; margin-bottom: 8px;">{title} ({p_str})</p>
            <p style="color: white; font-size: 46px; font-weight: bold; margin: 0;">{data['燈號']}</p>
            <p style="color: #4CAF50; font-size: 22px; margin-top: 10px; font-weight: bold;">↑ 指數帶寬: {bw_str}</p>
        </div>
    """, unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1: draw_market_card("加權指數", m_env.get('上市'))
with c2: draw_market_card("OTC 指數", m_env.get('上櫃'))

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請貼入三竹股池資料", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner("同步掃描中..."):
        for code in codes:
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            is_otc = False
            if df.empty:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                is_otc = True
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                # 環境參數
                m_type = "上櫃" if is_otc else "上市"
                env = m_env.get(m_type)
                idx_bw = env['帶寬']
                
                # 個股指標計算
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                df['BW'] = (df['STD'] * 4) / df['20MA']
                
                today, yest = df.iloc[-1], df.iloc[-2]
                price, up, ma20, ma20_y = float(today['Close']), float(today['Upper']), float(today['20MA']), float(yest['20MA'])
                vol_amt = (float(today['Volume']) * price) / 100000000
                chg = (price - float(yest['Close'])) / float(yest['Close'])
                bw = float(today['BW'])
                ratio = bw / idx_bw if idx_bw > 0 else 0
                
                # --- ⚠️ 核心 ABCDE 策略校正 ⚠️ ---
                strategy = "⚪ 未達准入"
                
                # 通用基礎：1.突破上軌 2.月線斜率正 3.成交值 > 5億
                if price > up and ma20 > ma20_y and vol_amt >= 5:
                    
                    # 判斷 D/E 環境條件
                    is_de_env = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    
                    # 🚀 策略 D：大盤環境成立 + 個股帶寬 > 20% + 比值 0.8~1.2 + 漲幅 3~5%
                    if is_de_env and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05:
                        if "🟢 綠燈" in env['燈號']: strategy = "💎【D：帶寬共振】"
                        else: strategy = "⚠️ D受限(需綠燈)"

                    # 🚀 策略 E：大盤環境成立 + 個股帶寬 > 20% + 比值 1.2~2 + 漲幅 3~7%
                    elif is_de_env and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07:
                        if "🟢 綠燈" in env['燈號']: strategy = "🚀【E：超額擴張】"
                        else: strategy = "⚠️ E受限(需綠燈)"

                    # 🔥 策略 A：帶寬 5~10% + 漲幅 3~7% (全燈號准入)
                    elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07:
                        strategy = "🔥【A：潛龍爆發】"

                    # 🎯 策略 B：帶寬 10~20% + 漲幅 3~5% (綠燈/黃燈准入)
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05:
                        if "🔴 紅燈" not in env['燈號']: strategy = "🎯【B：海巡狙擊】"
                        else: strategy = "⚠️ B受限(紅燈禁買)"

                    # 🌊 策略 C：帶寬 20~40% + 漲幅 3~7% (僅限綠燈)
                    elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07:
                        if "🟢 綠燈" in env['燈號']: strategy = "🌊【C：瘋狗浪】"
                        else: strategy = "⚠️ C受限(需綠燈)"

                results.append({
                    "代碼": code, "名稱": stock_names.get(code, "未知"),
                    "判定": strategy, "個股帶寬": f"{bw:.2%}", "漲幅": f"{chg:.2%}", "成交值": f"{vol_amt:.1f}億", "比值": f"{ratio:.2f}"
                })
        
        if results: st.table(pd.DataFrame(results))
        else: st.warning("無有效代碼")
