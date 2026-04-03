import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64

# --- 1. 網頁配置與隱藏所有平台雜訊 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

def set_ui_cleanup(image_file):
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
            background-color: #0E1117;
        }}
        .stApp::before {{
            content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%;
            background-color: rgba(0, 0, 0, 0.65); z-index: -1;
        }}

        /* 凍結窗格：確保大盤與日期整組固定 */
        div[data-testid="stHorizontalBlock"] {{
            position: sticky; top: 0px; z-index: 1000;
            background-color: rgba(30, 30, 30, 0.5); 
            padding: 15px; border-radius: 12px;
            backdrop-filter: blur(12px);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}

        /* 徹底隱藏 Manage App 與所有 Streamlit 標籤 */
        header {{visibility: hidden !important;}}
        footer {{visibility: hidden !important;}}
        #MainMenu {{visibility: hidden !important;}}
        div[data-testid="stDecoration"] {{display:none !important;}}
        div[data-testid="manage-app-button"] {{display: none !important;}}
        .viewerBadge_container__1QS1n {{display: none !important;}}
        div[class^="viewerBadge_adapter"] {{display: none !important;}}
        /* 針對右下角所有可能的懸浮元素 */
        iframe[title="Manage app"] {{display: none !important;}}
        .stActionButton {{display: none !important;}}
        
        /* 表格區塊優化 */
        [data-testid="stDataFrame"] {{
            background-color: rgba(10, 10, 10, 0.95) !important;
            border: 1px solid #444;
            padding: 5px;
        }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖功能 ---
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

# --- 3. 🛡️ 官方名稱清單 (解決英文名稱) ---
@st.cache_data(ttl=86400)
def get_tw_official_names():
    mapping = {}
    try:
        # 使用證交所與櫃買中心數據源
        for mode in ["2", "4"]:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={mode}"
            r = requests.get(url, timeout=10)
            df = pd.read_html(r.text)[0]
            for item in df.iloc[:, 0]:
                parts = str(item).split('\u3000') # 分割代碼與中文名
                if len(parts) >= 2:
                    mapping[parts[0].strip()] = parts[1].strip()
    except: pass
    return mapping

stock_name_map = get_tw_official_names()

# --- 4. 大盤環境 ---
@st.cache_data(ttl=300)
def get_market_env():
    res = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in indices.items():
        try:
            df = yf.download(v, period="2mo", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            c, m5, m20 = df['Close'].iloc[-1], df['Close'].rolling(5).mean().iloc[-1], df['Close'].rolling(20).mean().iloc[-1]
            bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / m20
            light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": float(c), "帶寬": float(bw)}
        except: res[k] = {"燈號": "⚠️", "價格": 0, "帶寬": 0}
    return res

m_env = get_market_env()

# --- 5. 主畫面佈局 (凍結區) ---
st.markdown("### 🏹 私密戰情室：姊布林ABCDE 策略判定")
m_col1, m_col2 = st.columns(2)
with m_col1:
    st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2:
    st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# 日期緊隨在大盤下
st.write(f"📅 **數據更新：{datetime.now().strftime('%Y/%m/%d %H:%M')}**")

# 側邊欄
st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請輸入股票代碼", height=250)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("正在對接官方資料庫並計算策略..."):
        for code in codes:
            # 強制校正：若官方對照表有，就絕不用 Yahoo 的英文名
            official_name = stock_name_map.get(code)
            
            df = yf.download(f"{code}.TW", period="2mo", progress=False)
            m_type = "上市"
            if df.empty:
                df = yf.download(f"{code}.TWO", period="2mo", progress=False)
                m_type = "上櫃"
            
            # 如果還是找不到名稱，從 yf 抓取後強制過濾英文字母
            if not official_name:
                try:
                    tk = yf.Ticker(f"{code}.TW")
                    raw_name = tk.info.get('shortName', "未知")
                    official_name = re.sub(r'[A-Za-z\s]+', '', raw_name) if raw_name != "未知" else "未知"
                except: official_name = "未知"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                env = m_env[m_type]
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                bw = (df['STD'].iloc[-1] * 4) / df['20MA'].iloc[-1]
                p_curr, p_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                
                # 判定邏輯
                res_tag = "⚪ 未達准入"
                if p_curr > df['Upper'].iloc[-1] and df['20MA'].iloc[-1] > df['20MA'].iloc[-2] and vol_amt >= 5:
                    if bw > 0.2 and 0.8 <= ratio <= 1.2: res_tag = "💎【D：帶寬共振】"
                    elif bw > 0.2 and ratio > 1.2: res_tag = "🚀【E：超額擴張】"
                    elif 0.05 <= bw <= 0.1: res_tag = "🔥【A：潛龍爆發】"
                    elif 0.1 < bw <= 0.2: res_tag = "🎯【B：海龍狙擊】"
                    elif 0.2 < bw <= 0.4: res_tag = "🌊【C：瘋狗浪】"

                results.append({
                    "代碼": code, "台股名稱": official_name, "判定結果": res_tag, 
                    "個股帶寬%": round(bw*100, 2), "今日漲幅%": round(chg*100, 2), 
                    "成交值(億)": round(vol_amt, 1), "對比比值": round(ratio, 2)
                })
        
        if results:
            st.markdown("#### 📊 判定結果清單 (點擊標題可排序)")
            st.dataframe(
                pd.DataFrame(results), 
                use_container_width=True, hide_index=True,
                column_config={
                    "個股帶寬%": st.column_config.NumberColumn(format="%.2f%%"),
                    "今日漲幅%": st.column_config.NumberColumn(format="%.2f%%")
                }
            )
