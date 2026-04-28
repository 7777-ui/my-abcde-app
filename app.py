import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 0. 核心數據函數 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        patterns = [r'"regularMarketPrice":\s*([0-9.]+)', r'"price":\s*"([0-9,.]+)"']
        for p in patterns:
            match = re.search(p, response.text)
            if match:
                val = float(match.group(1).replace(',', ''))
                if val > 0: return val
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

def get_local_revenue(year_month):
    """【關鍵修正】讀取資料夾內的營收檔案"""
    # 根據截圖，資料夾名稱為 "每月營收資料"
    folder = "每月營收資料"
    dfs = []
    for prefix in ["TWSE", "TPEX"]:
        # 拼湊路徑如: 每月營收資料/TWSE_202603.csv
        file_path = os.path.join(folder, f"{prefix}_{year_month}.csv")
        if os.path.exists(file_path):
            try:
                try: df = pd.read_csv(file_path, encoding='utf-8-sig')
                except: df = pd.read_csv(file_path, encoding='cp950')
                df.columns = [str(c).replace(" ", "") for c in df.columns]
                if '去年同月增減(%)' in df.columns:
                    dfs.append(df[['公司代號', '公司名稱', '去年同月增減(%)']])
            except: pass
    return pd.concat(dfs).drop_duplicates(subset=['公司代號']) if dfs else pd.DataFrame()

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

def set_ui_cleanup(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
        st.markdown(f"""
        <style>
        .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
        .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
        .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; }}
        </style>
        """, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": st.session_state.password_correct = True; st.rerun()
    st.stop()

# --- 3. 🛡️ 族群資料與大盤偵測 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                try: df = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df = pd.read_csv(f_name, encoding='cp950')
                df = df.fillna('-')
                for _, row in df.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "族群細分": str(row.iloc[4]).strip()}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    for k, (rt, yf_id) in {"上市": ("TSE", "^TWII"), "上櫃": ("OTC", "^TWOII")}.items():
        p = get_realtime_price(rt)
        df = get_historical_data(yf_id)
        if not df.empty and p:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            df = df.dropna(subset=['Close'])
            base = df['Close'].iloc[-20:-1].tolist() if df.index[-1].date() >= datetime.now().date() else df['Close'].iloc[-19:].tolist()
            c20 = base + [p]
            m20 = sum(c20)/20; bw = (pd.Series(c20).std()*4)/m20 if m20 != 0 else 0
            light = "🟢 綠燈" if p > sum(c20[-5:])/5 else ("🟡 黃燈" if p > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": p, "帶寬": bw}
        else: res[k] = {"燈號": "⚠️ 斷訊", "價格": 0, "帶寬": 0}
    return res
m_env = get_market_env()

# --- 4. 主畫面 UI ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 5. 側邊欄與模式控制 ---
st.sidebar.title("🛠️ 設定區")
mode = st.sidebar.radio("切換策略模式", ["🏹 姊布林掃描", "📈 營收動能 (年增>20%)"])

if mode == "🏹 姊布林掃描":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描"):
        # 這裡執行您原本的姊布林邏輯...
        st.info("執行姊布林掃描中...")

elif mode == "📈 營收動能 (年增>20%)":
    if st.sidebar.button("🔍 執行營收掃描"):
        now = datetime.now()
        # 抓取最近三個月 (3月, 2月, 1月)
        yms = [(now.replace(day=1) - timedelta(days=i*28)).strftime("%Y%m") for i in range(1, 4)]
        
        rev_dfs = [get_local_revenue(ym) for ym in yms]
        rev_dfs = [d for d in rev_dfs if not d.empty]
        
        if len(rev_dfs) == 3:
            final = rev_dfs[0].rename(columns={'去年同月增減(%)': 'm1'})
            final = pd.merge(final, rev_dfs[1][['公司代號', '去年同月增減(%)']].rename(columns={'去年同月增減(%)': 'm2'}), on='公司代號')
            final = pd.merge(final, rev_dfs[2][['公司代號', '去年同月增減(%)']].rename(columns={'去年同月增減(%)': 'm3'}), on='公司代號')
            final['平均年增%'] = final[['m1', 'm2', 'm3']].mean(axis=1)
            
            winners = final[final['平均年增%'] > 20.0].sort_values('平均年增%', ascending=False)
            
            res_list = []
            status = st.empty()
            for i, (idx, row) in enumerate(winners.iterrows()):
                code = str(row['公司代號']).strip()
                status.text(f"掃描報價中 ({i+1}/{len(winners)}): {code}")
                p_curr = get_realtime_price(code)
                if p_curr:
                    res_list.append({"代號": code, "簡稱": row['公司名稱'], "三月平均年增%": f"{row['平均年增%']:.1f}%", "現價": p_curr})
            st.session_state.rev_results = pd.DataFrame(res_list)
            status.empty()
        else:
            st.warning(f"資料夾內找不到足夠的營收檔案 (需含: {', '.join(yms)})")

if "rev_results" in st.session_state and mode == "📈 營收動能 (年增>20%)":
    st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)
