import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

# --- 2. CSS 精調版 (調整透明度與凍結座標) ---
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
            background-color: rgba(0, 0, 0, 0.6); 
            z-index: -1;
        }}

        /* 凍結窗格優化：讓大盤與日期同步固定 */
        [data-testid="stHeader"] {{ background: rgba(0,0,0,0); }}
        
        /* 調整大盤區塊：反黑減輕，透明度增加 */
        div[data-testid="stHorizontalBlock"] {{
            position: sticky;
            top: 0px;
            z-index: 1000;
            background-color: rgba(30, 30, 30, 0.6); /* 這裡調淺了 */
            padding: 10px 10px;
            border-bottom: 1px solid rgba(76, 175, 80, 0.3);
            backdrop-filter: blur(5px);
        }}

        /* 表格區塊底色 */
        [data-testid="stDataFrame"] {{
            background-color: rgba(15, 15, 15, 0.9) !important;
            margin-top: 10px;
        }}
        
        header {{ visibility: hidden; }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_bg_fixed("header_image.png")

# --- 3. 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

if not st.session_state.password_correct:
    st.title("🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 4. 絕對台股名稱抓取 (官方來源) ---
@st.cache_data(ttl=86400)
def get_official_tw_names():
    names = {}
    try:
        # 抓取上市與上櫃官方清單
        for url in ["https://isin.twse.com.tw/isin/C_public.jsp?strMode=2", 
                    "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"]:
            res = requests.get(url)
            df = pd.read_html(res.text)[0]
            for val in df.iloc[:, 0]:
                parts = str(val).split('\u3000')
                if len(parts) >= 2:
                    names[parts[0].strip()] = parts[1].strip()
    except: pass
    return names

stock_db = get_official_tw_names()

# --- 5. 大盤燈號 ---
@st.cache_data(ttl=300)
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
            p, bw = float(curr['Close']), float(curr['BW'])
            
            if p > float(curr['5MA']): light = "🟢 綠燈"
            elif p > float(curr['20MA']): light = "🟡 黃燈"
            else: light = "🔴 紅燈"
            status[name] = {"燈號": light, "價格": p, "帶寬": bw}
        except: status[name] = {"燈號": "⚠️", "價格": 0.0, "帶寬": 0.0}
    return status

# --- 6. 介面佈局 ---
# 大盤凍結區
m_env = get_market_status()
m_col1, m_col2 = st.columns(2)
with m_col1:
    d1 = m_env['上市']
    st.metric(f"加權指數 ({d1['價格']:,.2f})", d1['燈號'], f"帶寬: {d1['帶寬']:.2%}")
with m_col2:
    d2 = m_env['上櫃']
    st.metric(f"OTC 指數 ({d2['價格']:,.2f})", d2['燈號'], f"帶寬: {d2['帶寬']:.2%}")

# 日期列 (緊貼在大盤下方)
st.markdown(f"📅 **掃描日期：{datetime.now().strftime('%Y/%m/%d')}**")

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請輸入股票代碼", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("同步台股名稱與分析中..."):
        for code in codes:
            # 強制使用中文資料庫名稱
            name = stock_db.get(code, "未知")
            
            # 下載數據
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 20:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                m_type = "上櫃"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                env = m_env[m_type]
                
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                df['BW'] = (df['STD'] * 4) / df['20MA']
                
                today, yest = df.iloc[-1], df.iloc[-2]
                price, vol_amt = float(today['Close']), (float(today['Volume']) * float(today['Close'])) / 100000000
                chg, bw = (price - float(yest['Close'])) / float(yest['Close']), float(today['BW'])
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                
                strategy = "⚪ 未達准入"
                if price > float(today['Upper']) and float(today['20MA']) > float(yest['20MA']) and vol_amt >= 5:
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
                    "代碼": code, "名稱": name, "策略判定": strategy, 
                    "個股帶寬%": round(bw*100, 2), "漲幅%": round(chg*100, 2), 
                    "成交值(億)": round(vol_amt, 1), "帶寬比值": round(ratio, 2)
                })
        
        if results:
            # 這裡就是你要的中文化篩選介面
            st.dataframe(
                pd.DataFrame(results), 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "代碼": st.column_config.TextColumn("股票代碼"),
                    "名稱": st.column_config.TextColumn("台股名稱"),
                    "策略判定": st.column_config.TextColumn("判定結果"),
                    "個股帶寬%": st.column_config.NumberColumn("個股帶寬 %", format="%.2f"),
                    "漲幅%": st.column_config.NumberColumn("今日漲幅 %", format="%.2f"),
                    "成交值(億)": st.column_config.NumberColumn("成交值 (億)"),
                    "帶寬比值": st.column_config.NumberColumn("對比指數比值")
                }
            )
