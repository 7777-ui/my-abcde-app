import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")

# 設定自動刷新：每 5 分鐘觸發一次內部 Rerun
st_autorefresh(interval=300000, key="datarefresh")

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

# --- 2. 🔐 密碼鎖與登出功能 ---
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

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()

# --- 3. 🛡️ 本地 CSV 讀取 ---
@st.cache_data(ttl=604800)
def get_names_from_local_files():
    mapping = {}
    files = ["TWSE.csv", "TPEX.csv"] 
    for f_name in files:
        if os.path.exists(f_name):
            try:
                try:
                    df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except:
                    df_local = pd.read_csv(f_name, encoding='cp950')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    name = str(row.iloc[2]).strip()
                    if code.isdigit(): mapping[code] = name
            except: pass
    return mapping

stock_name_map = get_names_from_local_files()

# --- 4. 大盤環境偵測 (終極強韌版：三重備援機制) ---
@st.cache_data(ttl=300)
def get_market_env():
    res = {}
    # 定義每個指數的優先嘗試清單
    target_indices = {
        "上市": ["^TWII", "000001.SS"], 
        "上櫃": ["OTC.TWO", "000620.TWO", "^TPEX"]  # OTC.TWO 通常最穩定
    }

    for k, v_list in target_indices.items():
        df = pd.DataFrame()
        success_code = ""
        
        # 依序嘗試清單中的代碼
        for code in v_list:
            try:
                temp_df = yf.download(code, period="5mo", progress=False)
                if not temp_df.empty and len(temp_df) >= 20:
                    df = temp_df
                    success_code = code
                    break # 抓到數據了，跳出嘗試循環
            except:
                continue
        
        try:
            if not df.empty:
                if isinstance(df.columns, pd.MultiIndex): 
                    df.columns = df.columns.get_level_values(0)
                
                df = df.dropna(subset=['Close'])
                c = df['Close'].iloc[-1]
                m5 = df['Close'].rolling(5).mean().iloc[-1]
                m20 = df['Close'].rolling(20).mean().iloc[-1]
                std_val = df['Close'].rolling(20).std().iloc[-1]
                
                # 計算帶寬，並確保不是 nan
                bw = (std_val * 4) / m20 if not pd.isna(std_val) and m20 != 0 else 0.0
                
                # 燈號邏輯
                light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": float(c), "帶寬": float(bw)}
            else:
                res[k] = {"燈號": "⚠️ 數據源異常", "價格": 0.0, "帶寬": 0.0}
        except:
            res[k] = {"燈號": "⚠️ 計算錯誤", "價格": 0.0, "帶寬": 0.0}
            
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
            official_name = stock_name_map.get(code)
            df = yf.download(f"{code}.TW", period="4mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 10:
                df = yf.download(f"{code}.TWO", period="4mo", progress=False)
                m_type = "上櫃"

            if not official_name: official_name = f"台股 {code}"

            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                env = m_env[m_type]
                df['20MA'] = df['Close'].rolling(20).mean()
                df['Upper'] = df['20MA'] + (df['Close'].rolling(20).std() * 2)
                
                p_curr, p_yest = df['Close'].iloc[-1], df['Close'].iloc[-2]
                std_ind = df['Close'].rolling(20).std().iloc[-1]
                bw = (std_ind * 4) / df['20MA'].iloc[-1] if not pd.isna(std_ind) else 0.0
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                ratio = bw / env['帶寬'] if env['帶寬'] > 0 else 0
                slope_pos = df['20MA'].iloc[-1] > df['20MA'].iloc[-2]
                break_upper = p_curr > df['Upper'].iloc[-1]
                
                # --- 新增：判定原因邏輯 ---
                res_tag = ""
                fail_reasons = []

                if not break_upper: fail_reasons.append("未站上布林上軌")
                if not slope_pos: fail_reasons.append("20MA 斜率向下")
                if vol_amt < 5: fail_reasons.append(f"量能不足({vol_amt:.1f}億)")

                if not fail_reasons:
                    env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    # 判定邏輯
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
                    
                    if not res_tag:
                        res_tag = f"⚪ 參數不符(漲幅{chg*100:.1f}%/帶寬{bw*100:.1f}%)"
                else:
                    res_tag = "⚪ " + " / ".join(fail_reasons)

                results.append({
                    "代碼": code, "族群分類": official_name, "判定結果": res_tag, 
                    "個股帶寬%": f"{bw*100:.2f}%", "漲幅%": f"{chg*100:.2f}%", 
                    "成交值(億)": round(vol_amt, 1), "對比比值": round(ratio, 2)
                })
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)
