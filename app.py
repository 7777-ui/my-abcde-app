import streamlit as st
import yfinance as yf
import pandas as pd
import re
import requests
from datetime import datetime
import os
import base64
import pytz

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.     b64encode(f.read()).decode()
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

# --- 3. 🛡️ 本地 CSV 讀取 (對應檔案：TWSE.csv 與 TPEX.csv) ---
@st.cache_data(ttl=604800)
def get_names_from_local_files():
    mapping = {}
    # 根據 GitHub 顯示的完整檔名進行對應
    files = ["TWSE.csv", "TPEX.csv"] 
    
    for f_name in files:
        if os.path.exists(f_name):
            try:
                # 優先嘗試 utf-8-sig，失敗則嘗試 cp950
                try:
                    df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except:
                    df_local = pd.read_csv(f_name, encoding='cp950')
                
                # 抓取邏輯：第一欄為代碼，第二欄為名稱
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    name = str(row.iloc[2]).strip()
                    if code.isdigit():
                        mapping[code] = name
            except: pass
    return mapping

stock_name_map = get_names_from_local_files()

# --- 4. 大盤環境偵測 (修正版) ---
@st.cache_data(ttl=300) # 每 5 分鐘允許更新一次
def get_market_env():
    res = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in indices.items():
        try:
            # 增加下載的天數確保有足夠數據計算 20MA
            df = yf.download(v, period="5d", interval="1m", progress=False) 
            if df.empty:
                # 如果分時數據抓不到，改抓日線
                df = yf.download(v, period="1mo", progress=False)
            
            if isinstance(df.columns, pd.MultiIndex): 
                df.columns = df.columns.get_level_values(0)
            
            # 關鍵修正：移除 NaN 掉的列，並取最後一個有效數值
            df = df.dropna(subset=['Close'])
            
            c = float(df['Close'].iloc[-1])
            # 計算 5MA 與 20MA (這裡需要較長天數數據)
            df_daily = yf.download(v, period="3mo", progress=False)
            if isinstance(df_daily.columns, pd.MultiIndex): 
                df_daily.columns = df_daily.columns.get_level_values(0)
            
            m5 = df_daily['Close'].rolling(5).mean().iloc[-1]
            m20 = df_daily['Close'].rolling(20).mean().iloc[-1]
            std20 = df_daily['Close'].rolling(20).std().iloc[-1]
            
            bw = (std20 * 4) / m20
            
            # 燈號判定邏輯
            light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": c, "帶寬": float(bw)}
        except Exception as e:
            res[k] = {"燈號": "⚠️ 錯誤", "價格": 0.0, "帶寬": 0.0}
    return res

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
            # 直接從 CSV 對照表拿名字
            official_name = stock_name_map.get(code)
            
            # 下載個股數據（用於 ABCDE 判定）
            df = yf.download(f"{code}.TW", period="3mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 10:
                df = yf.download(f"{code}.TWO", period="3mo", progress=False)
                m_type = "上櫃"

            # 若對照表依然沒抓到（例如剛掛牌的新股），顯示保險名稱
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
