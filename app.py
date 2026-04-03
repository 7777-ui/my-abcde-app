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

def set_ui_final_fix(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            img_data = f.read()
        b64_encoded = base64.b64encode(img_data).decode()
        # 加入強力的 CSS 覆蓋，徹底移除 Manage App 與簡化 UI
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
            background-color: rgba(0, 0, 0, 0.6); z-index: -1;
        }}

        /* 凍結窗格：大盤資訊 */
        div[data-testid="stHorizontalBlock"] {{
            position: sticky; top: 0px; z-index: 1000;
            background-color: rgba(40, 40, 40, 0.4); 
            padding: 15px; border-radius: 12px;
            backdrop-filter: blur(10px);
        }}

        /* 🔴 徹底隱藏 Manage App (針對所有可能變化的 class) */
        [data-testid="manage-app-button"], 
        .stManageAppButton, 
        iframe[title="Manage app"], 
        footer, header, 
        #MainMenu {{ display: none !important; visibility: hidden !important; }}

        /* 表格區塊優化 */
        [data-testid="stDataFrame"] {{
            background-color: rgba(10, 10, 10, 0.95) !important;
            border: 1px solid #444;
        }}
        </style>
        """
        st.markdown(style, unsafe_allow_html=True)

set_ui_final_fix("header_image.png")

# --- 2. 🔐 密碼鎖 (回歸) ---
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

# --- 3. 🛡️ 官方台股名稱清單 (解決名稱未知/英文) ---
@st.cache_data(ttl=86400)
def get_tw_stock_names():
    mapping = {}
    try:
        # 直接抓取證交所官方清單
        for m in ["2", "4"]:
            url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={m}"
            res = requests.get(url, timeout=10)
            df = pd.read_html(res.text)[0]
            for val in df.iloc[:, 0]:
                parts = str(val).split('\u3000') # 全形空格
                if len(parts) >= 2:
                    mapping[parts[0].strip()] = parts[1].strip()
    except: pass
    return mapping

stock_db = get_tw_stock_names()

# --- 4. 大盤環境與燈號 ---
@st.cache_data(ttl=300)
def get_market_context():
    res = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in indices.items():
        try:
            df = yf.download(v, period="2mo", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            c = df['Close'].iloc[-1]
            m5 = df['Close'].rolling(5).mean().iloc[-1]
            m20 = df['Close'].rolling(20).mean().iloc[-1]
            bw = (df['Close'].rolling(20).std().iloc[-1] * 4) / m20
            
            # 根據策略定義燈號
            if c > m5: light = "🟢 綠燈"
            elif c > m20: light = "🟡 黃燈"
            else: light = "🔴 紅燈"
            
            res[k] = {"燈號": light, "價格": float(c), "帶寬": float(bw)}
        except: res[k] = {"燈號": "⚠️", "價格": 0, "帶寬": 0}
    return res

m_env = get_market_context()

# --- 5. 主畫面執行 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1:
    st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2:
    st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

st.write(f"📅 **數據更新：{datetime.now().strftime('%Y/%m/%d %H:%M')}**")

# 側邊欄
st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("請輸入股票代碼", height=250)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("策略同步分析中..."):
        for code in codes:
            # 1. 解決名稱問題：優先查表，查不到才過濾 Yahoo 英文
            name = stock_db.get(code)
            if not name:
                try:
                    tk = yf.Ticker(f"{code}.TW")
                    raw_n = tk.info.get('shortName', "未知")
                    name = re.sub(r'[A-Za-z\s]+', '', raw_n) # 刪除英文字母
                except: name = "未知"

            # 下載個股數據
            df = yf.download(f"{code}.TW", period="3mo", progress=False)
            m_type = "上市"
            if df.empty:
                df = yf.download(f"{code}.TWO", period="3mo", progress=False)
                m_type = "上櫃"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                env = m_env[m_type]
                
                # 計算個股指標
                df['20MA'] = df['Close'].rolling(20).mean()
                df['STD'] = df['Close'].rolling(20).std()
                df['Upper'] = df['20MA'] + (df['STD'] * 2)
                
                p_curr = df['Close'].iloc[-1]
                p_yest = df['Close'].iloc[-2]
                bw = (df['STD'].iloc[-1] * 4) / df['20MA'].iloc[-1]
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                slope_pos = df['20MA'].iloc[-1] > df['20MA'].iloc[-2] # 20MA 斜率為正
                break_upper = p_curr > df['Upper'].iloc[-1] # 突破布林上軌
                
                res_tag = "⚪ 未達准入"
                
                # 核心准入檢查：突破上軌 + 20MA上揚 + 成交量>5億
                if break_upper and slope_pos and vol_amt >= 5:
                    # 💡 策略 D & E 優先判定 (需大盤帶寬滿足)
                    env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    
                    if "🟢 綠燈" in env['燈號']:
                        if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05:
                            res_tag = "💎【D：帶寬共振】"
                        elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07:
                            res_tag = "🚀【E：超額擴張】"
                        elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07:
                            res_tag = "🔥【A：潛龍爆發】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05:
                            res_tag = "🎯【B：海龍狙擊】"
                        elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07:
                            res_tag = "🌊【C：瘋狗浪】"
                            
                    elif "🟡 黃燈" in env['燈號']:
                        # 黃燈僅限 A, B
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07:
                            res_tag = "🔥【A：潛龍爆發】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05:
                            res_tag = "🎯【B：海龍狙擊】"
                            
                    elif "🔴 紅燈" in env['燈號']:
                        # 紅燈僅限 A
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07:
                            res_tag = "🔥【A：潛龍爆發】"

                results.append({
                    "代碼": code, "台股名稱": name, "判定結果": res_tag, 
                    "個股帶寬%": round(bw*100, 2), "漲幅%": round(chg*100, 2), 
                    "成交值(億)": round(vol_amt, 1), "對比比值": round(ratio, 2)
                })
        
        if results:
            st.dataframe(
                pd.DataFrame(results), 
                use_container_width=True, hide_index=True,
                column_config={"個股帶寬%": st.column_config.NumberColumn(format="%.2f%%"),
                               "漲幅%": st.column_config.NumberColumn(format="%.2f%%")}
            )
