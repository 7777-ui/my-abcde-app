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

st_autorefresh(interval=300000, key="datarefresh")

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    /* 背景設置 */
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    
    /* 修正頂部空白：強制主容器與頂部對齊 */
    [data-testid="stAppViewMain"] > div:first-child {{ padding-top: 0rem !important; }}
    .stMainBlockContainer {{ padding-top: 1.5rem !important; padding-bottom: 1rem !important; }}
    
    /* 隱藏不必要的 UI 元素 */
    [data-testid="manage-app-button"], .stManageAppButton, iframe[title="Manage app"], footer, #MainMenu {{ display: none !important; }}
    header {{ background: transparent !important; height: 3rem !important; }} 
    
    /* 大盤戰情區塊：半透明模糊效果 */
    div[data-testid="stHorizontalBlock"] {{ 
        position: sticky; 
        top: 0px; 
        z-index: 1000; 
        background-color: rgba(30, 30, 30, 0.6); 
        padding: 15px; 
        border-radius: 12px; 
        backdrop-filter: blur(10px); 
        margin-top: -10px; 
    }}
    
    /* 表格背景強化 */
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; padding: 5px; }}
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

# --- 3. 🛡️ 族群 CSV 深度讀取 (修正 nan 問題) ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    files = ["TWSE.csv", "TPEX.csv"] 
    for f_name in files:
        if os.path.exists(f_name):
            try:
                try:
                    df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except:
                    df_local = pd.read_csv(f_name, encoding='cp950')
                
                df_local = df_local.fillna('-')
                
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping

stock_info_map = get_stock_info_full()

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=300)
def get_market_env():
    res = {}
    indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in indices.items():
        try:
            df = yf.download(v, period="4mo", progress=False)
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Close'])
            c = df['Close'].iloc[-1]
            m5 = df['Close'].rolling(5).mean().iloc[-1]
            m20 = df['Close'].rolling(20).mean().iloc[-1]
            std_val = df['Close'].rolling(20).std().iloc[-1]
            bw = (std_val * 4) / m20 if not pd.isna(std_val) and m20 != 0 else 0.0
            light = "🟢 綠燈" if c > m5 else ("🟡 黃燈" if c > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": float(c), "帶寬": bw}
        except:
            res[k] = {"燈號": "⚠️ 延遲數據", "價格": 0.0, "帶寬": 0.0}
    return res

m_env = get_market_env()

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M')}**")

st.sidebar.title("🛠️ 設定區")
raw_input = st.sidebar.text_area("輸入股票代碼", height=200)

if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    
    with st.spinner("分析中..."):
        for code in codes:
            info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
            df = yf.download(f"{code}.TW", period="4mo", progress=False)
            m_type = "上市"
            if df.empty or len(df) < 10:
                df = yf.download(f"{code}.TWO", period="4mo", progress=False)
                m_type = "上櫃"

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
                
                res_tag = ""
                fail_reasons = []
                if not break_upper: fail_reasons.append("未站上軌")
                if not slope_pos: fail_reasons.append("斜率負")
                if vol_amt < 5: fail_reasons.append(f"量不足")

                if not fail_reasons:
                    env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                    if "🟢" in env['燈號']:
                        if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：共振】"
                        elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額】"
                        elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                    elif "🟡" in env['燈號'] or "🔴" in env['燈號']:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                    
                    if not res_tag: res_tag = "⚪ 參數不符"
                else:
                    res_tag = "⚪ " + "/".join(fail_reasons)

                results.append({
                    "代號": code,
                    "名稱": info["簡稱"],
                    "策略": res_tag,
                    "漲幅%": f"{chg*100:.1f}%",
                    "成交值(億)": round(vol_amt, 1),
                    "個股帶寬%": f"{bw*100:.2f}%",
                    "比值": round(ratio, 2),
                    "產業排位": info["產業排位"],
                    "2026指標": info["實力指標"],
                    "族群細分": info["族群細分"],
                    "關鍵技術/報價": info["關鍵技術"]
                })
        
        if results:
            df_res = pd.DataFrame(results)
            # --- 核心優化：凍結前兩欄 ---
            st.dataframe(
                df_res, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "代號": st.column_config.TextColumn("代號", pinned=True),
                    "名稱": st.column_config.TextColumn("名稱", pinned=True)
                }
            )

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
