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

# --- 2. 背景與表格視覺優化 ---
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
        
        /* 表格深色底色優化：讓字體更直覺清晰 */
        .stTable {{
            background-color: rgba(20, 20, 20, 0.85) !important;
            border-radius: 10px;
            padding: 10px;
        }}
        .stTable td, .stTable th {{
            color: white !important;
            font-size: 16px !important;
        }}
        
        header {{ visibility: hidden; }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_bg_fixed("header_image.png")

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

# --- 4. 名稱抓取校正 (增加錯誤處理與清理) ---
@st.cache_data
def get_stock_names():
    res = {}
    urls = [
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", # 上市
        "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"  # 上櫃
    ]
    for url in urls:
        try:
            response = requests.get(url, timeout=10)
            dfs = pd.read_html(response.text)
            df = dfs[0]
            for val in df.iloc[:, 0]:
                parts = str(val).split('\u3000')
                if len(parts) >= 2:
                    res[parts[0].strip()] = parts[1].strip()
        except:
            continue
    return res

stock_names = get_stock_names()

# --- 5. 大盤偵測 ---
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
            p, m5, m20, bw = float(curr['Close']), float(curr['5MA']), float(curr['20MA']), float(curr['BW'])
            if p > m5: light = "🟢 綠燈"
            elif p > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
            status[name] = {"燈號": light, "價格": p, "帶寬": bw}
        except: status[name] = {"燈號": "⚠️ 偵測中", "價格": 0.0, "帶寬": 0.0}
    return status

# --- 6. 介面與掃描 ---
st.title("🏹 私密戰情室：姊布林ABCDE 策略判定")
m_env = get_market_status()

c1, c2 = st.columns(2)
with c1:
    d = m_env.get('上市')
    st.metric(f"加權指數 ({d['價格']:,.2f})", d['燈號'], f"帶寬: {d['帶寬']:.2%}")
with c2:
    d = m_env.get('上櫃')
    st.metric(f"OTC 指數 ({d['價格']:,.2f})", d['燈號'], f"帶寬: {d['帶寬']:.2%}")

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請輸入股票代碼", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    with st.spinner("戰情分析中..."):
        for code in codes:
            # 優先嘗試上市 (.TW)，失敗則試上櫃 (.TWO)
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 20:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                m_type = "上櫃"
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                
                env = m_env.get(m_type)
                idx_bw = env['帶寬']
                
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
                
                strategy = "⚪ 未達准入"
                if price > up and ma20 > ma20_y and vol_amt >= 5:
                    is_de_env = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    
                    if is_de_env and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05:
                        strategy = "💎【D：帶寬共振】" if "🟢 綠燈" in env['燈號'] else "⚠️ D受限(需綠燈)"
                    elif is_de_env and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07:
                        strategy = "🚀【E：超額擴張】" if "🟢 綠燈" in env['燈號'] else "⚠️ E受限(需綠燈)"
                    elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07:
                        strategy = "🔥【A：潛龍爆發】"
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05:
                        strategy = "🎯【B：海龍狙擊】" if "🔴 紅燈" not in env['燈號'] else "⚠️ B受限(紅燈禁買)"
                    elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07:
                        strategy = "🌊【C：瘋狗浪】" if "🟢 綠燈" in env['燈號'] else "⚠️ C受限(需綠燈)"

                results.append({
                    "代碼": code, 
                    "名稱": stock_names.get(code, "未知"),
                    "判定": strategy, 
                    "個股帶寬": f"{bw:.2%}", 
                    "漲幅": f"{chg:.2%}", 
                    "成交值": f"{vol_amt:.1f}億", 
                    "比值": f"{ratio:.2f}"
                })
        
        if results:
            st.table(pd.DataFrame(results))
        else:
            st.warning("查無標的資料")
