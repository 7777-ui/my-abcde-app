import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
import time
import os
import base64

# --- 1. 設置網頁配置 ---
st.set_page_config(
    page_title="🏹 姊布林ABCDE 戰情室",
    page_icon="🏹",
    layout="wide"
)

# --- 2. 核心：自適應背景圖片函數 (徹底解決大小不適應問題) ---
def set_bg_fixed_responsive(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            img_data = f.read()
        b64_encoded = base64.b64encode(img_data).decode()
        style = f"""
        <style>
        .stApp {{
            background-image: url("data:image/png;base64,{b64_encoded}");
            background-attachment: fixed;
            
            /* 關鍵：自適應縮放 */
            background-size: cover; /* 如果要完全填滿不留白(可能會切圖)用 cover */
            /* 備選：如果想看到整張圖(可能會留白)用 contain */
            
            background-position: center center; /* 固定置中 */
            background-repeat: no-repeat;
        }}
        
        /* 增加一層半透明黑遮罩，確保文字與燈號清晰 */
        .stApp::before {{
            content: "";
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.65); /* 稍微加深遮罩，質感更好 */
            z-index: -1;
        }}
        
        /* 隱藏預設頭部，視覺更乾淨 */
        header {{
            visibility: hidden;
        }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

# 執行背景設定
set_bg_fixed_responsive("header_image.png")

# --- 3. 密碼鎖 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    st.title("🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    return False

if not check_password():
    st.stop()

# --- 4. 核心抓取邏輯 (快取名稱表) ---
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

# --- 5. 大盤環境偵測 ---
def get_market_status():
    status = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for name, sym in indices.items():
        try:
            df = yf.download(sym, period="2mo", interval="1d", progress=False)
            if df.empty:
                time.sleep(1)
                df = yf.download(sym, period="2mo", interval="1d", progress=False)
            
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            
            df['5MA'] = df['Close'].rolling(5).mean()
            df['20MA'] = df['Close'].rolling(20).mean()
            df['STD'] = df['Close'].rolling(20).std()
            df['BW'] = (df['STD'] * 4) / df['20MA']
            
            valid_df = df.dropna(subset=['Close', '5MA', '20MA', 'BW'])
            curr = valid_df.iloc[-1]
            
            price, m5, m20, bw = float(curr['Close']), float(curr['5MA']), float(curr['20MA']), float(curr['BW'])
            
            if price > m5: light = "🟢 綠燈"
            elif price > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
                
            status[name] = {"燈號": light, "價格": price, "帶寬": bw}
        except:
            status[name] = {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0}
    return status

# --- 6. 介面執行 ---
st.title("🏹 私密戰情室：姊布林ABCDE 策略判定")
m_env = get_market_status()

# 自定義卡片顯示組件 (調整半透明度與間距，視覺更統一)
def draw_market_card(title, data):
    price_str = f"{data['價格']:,.2f}" if data['價格'] > 0 else "---"
    bw_str = f"{data['帶寬']:.2%}"
    st.markdown(f"""
        <div style="background-color: rgba(30, 30, 30, 0.75); padding: 25px; border-radius: 12px; border-left: 6px solid #4CAF50; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.3);">
            <p style="color: #AAAAAA; font-size: 24px; margin-bottom: 8px;">{title} ({price_str})</p>
            <p style="color: white; font-size: 46px; font-weight: bold; margin: 0;">{data['燈號']}</p>
            <p style="color: #4CAF50; font-size: 22px; margin-top: 12px; font-weight: bold;">↑ 帶寬: {bw_str}</p>
        </div>
    """, unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    draw_market_card("加權指數", m_env.get('上市', {"燈號": "偵測中", "價格": 0.0, "帶寬": 0.0}))
with col2:
    draw_market_card("OTC 指數", m_env.get('上櫃', {"燈號": "偵測中", "價格": 0.0, "帶寬": 0.0}))

st.markdown("<br><hr><br>", unsafe_allow_html=True)

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請貼入三竹股池資料", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner("同步掃描分析中..."):
        for code in codes:
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            is_otc = False
            if df.empty:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                is_otc = True
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                
                market = "上櫃" if is_otc else "上市"
                env = m_env.get(market, {"燈號": "🔴 紅燈", "價格": 0.0, "帶寬": 0.0})
                
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                df['BW'] = (df['STD'] * 4) / df['20MA']
                
                today, yest = df.iloc[-1], df.iloc[-2]
                price = float(today['Close'])
                up = float(today['Upper'])
                ma20 = float(today['20MA'])
                ma20_y = float(yest['20MA'])
                vol_amt = (float(today['Volume']) * price) / 100000000
                chg = (price - float(yest['Close'])) / float(yest['Close'])
                bw = float(today['BW'])
                
                strategy = "⚪ 未達准入"
                if price > up and ma20 > ma20_y and vol_amt >= 5:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: 
                        strategy = "🔥【A：潛龍爆發】"
                    elif "🔴 紅燈" not in env['燈號'] and 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: 
                        strategy = "🎯【B：海巡狙擊】"
                    elif "🟢 綠燈" in env['燈號'] and bw >= 0.2: 
                        strategy = "🌊【C：瘋狗浪】"

                results.append({
                    "代碼": code, "名稱": stock_names.get(code, "未知"),
                    "判定": strategy, "個股帶寬": f"{bw:.2%}", "漲幅": f"{chg:.2%}", "成交值": f"{vol_amt:.1f}億"
                })
        
        if results:
            st.table(pd.DataFrame(results))
        else:
            st.warning("無有效股票代碼資料")
