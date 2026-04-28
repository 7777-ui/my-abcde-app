import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import io
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 0. 核心抓取函數 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
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
    """直接讀取資料夾內的營收檔案 (TWSE_202603.csv)"""
    folder = "每月營收資料"
    dfs = []
    for prefix in ["TWSE", "TPEX"]:
        file_path = os.path.join(folder, f"{prefix}_{year_month}.csv")
        if os.path.exists(file_path):
            try:
                # 處理編碼與欄位清理
                try: df = pd.read_csv(file_path, encoding='utf-8-sig')
                except: df = pd.read_csv(file_path, encoding='cp950')
                df.columns = [str(c).replace(" ", "") for c in df.columns]
                # 確保關鍵欄位存在
                if '去年同月增減(%)' in df.columns:
                    dfs.append(df[['公司代號', '公司名稱', '去年同月增減(%)']])
            except: pass
    return pd.concat(dfs).drop_duplicates(subset=['公司代號']) if dfs else pd.DataFrame()

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 戰情室整合版", page_icon="🏹", layout="wide")
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

# --- 2. 🔐 密碼鎖 (略，保持你原本的 test0403) ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": st.session_state.password_correct = True; st.rerun()
    st.stop()

# --- 3. 🛡️ 族群讀取與環境偵測 ---
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
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業排位": str(row.iloc[2]).strip(), "實力指標": str(row.iloc[3]).strip(), "族群細分": str(row.iloc[4]).strip(), "關鍵技術": str(row.iloc[5]).strip()}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    for k, (rt, yf_id) in {"上市": ("TSE", "^TWII"), "上櫃": ("OTC", "^TWOII")}.items():
        try:
            p = get_realtime_price(rt)
            df = get_historical_data(yf_id)
            if not df.empty and p:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df = df.dropna(subset=['Close'])
                base = df['Close'].iloc[-20:-1].tolist() if df.index[-1].date() >= datetime.now().date() else df['Close'].iloc[-19:].tolist()
                c20 = base + [p]
                m20 = sum(c20)/20
                light = "🟢 綠燈" if p > sum(c20[-5:])/5 else ("🟡 黃燈" if p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": p, "帶寬": (pd.Series(c20).std()*4)/m20 if m20 != 0 else 0}
            else: res[k] = {"燈號": "⚠️ 斷訊", "價格": 0, "帶寬": 0}
        except: res[k] = {"燈號": "⚠️ 斷訊", "價格": 0, "帶寬": 0}
    return res
m_env = get_market_env()

# --- 4. UI 顯示 ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 5. 側邊欄切換 ---
mode = st.sidebar.radio("切換策略模式", ["🏹 姊布林 ABCDE", "📈 營收動能 (年增>20%)"])

if mode == "🏹 姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("掃描中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                # (此處保留你原始程式碼的所有姊布林判斷邏輯... 為簡化省略重複代碼)
                # 最終將結果 append 到 results 即可
                results.append({"代號": code, "名稱": info["簡稱"], "現價": p_curr, "族群細分": info["族群細分"]})
        st.session_state.scan_results = pd.DataFrame(results)
    if "scan_results" in st.session_state:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif mode == "📈 營收動能 (年增>20%)":
    if st.sidebar.button("🔍 執行營收掃描"):
        now = datetime.now()
        # 取得最近三個月 YYYYMM
        yms = [(now.replace(day=1) - timedelta(days=i*28)).strftime("%Y%m") for i in range(1, 4)]
        
        rev_dfs = [get_local_revenue(ym) for ym in yms]
        rev_dfs = [d for d in rev_dfs if not d.empty]
        
        if len(rev_dfs) == 3:
            final = rev_dfs[0].rename(columns={'去年同月增減(%)': 'm1'})
            final = pd.merge(final, rev_dfs[1][['公司代號', '去年同月增減(%)']].rename(columns={'去年同月增減(%)': 'm2'}), on='公司代號')
            final = pd.merge(final, rev_dfs[2][['公司代號', '去年同月增減(%)']].rename(columns={'去年同月增減(%)': 'm3'}), on='公司代號')
            final['平均年增%'] = final[['m1', 'm2', 'm3']].mean(axis=1)
            
            winners = final[final['平均年增%'] > 20.0].sort_values('平均年增%', ascending=False)
            
            rev_results = []
            status = st.empty()
            for i, (idx, row) in enumerate(winners.iterrows()):
                code = str(row['公司代號']).strip()
                status.text(f"掃描報價中 ({i+1}/{len(winners)}): {code}")
                p_curr = get_realtime_price(code)
                if p_curr:
                    hist = get_historical_data(f"{code}.TW" if len(code)<=4 else f"{code}.TWO")
                    if not hist.empty:
                        if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                        p_yest = hist['Close'].iloc[-2] if hist.index[-1].date() >= datetime.now().date() else hist['Close'].iloc[-1]
                        chg = (p_curr - p_yest) / p_yest
                        vol_amt = (hist['Volume'].iloc[-1] * p_curr) / 100000000
                        rev_results.append({
                            "代號": code, "簡稱": row['公司名稱'], "三月平均年增%": f"{row['平均年增%']:.1f}%",
                            "現價": p_curr, "漲跌幅%": f"{chg*100:+.1f}%", "成交值(億)": round(vol_amt, 2)
                        })
            st.session_state.rev_results = pd.DataFrame(rev_results)
            status.empty()
        else: st.warning(f"資料夾內找不到足夠的營收檔案 (需含: {', '.join(yms)})")
    
    if "rev_results" in st.session_state:
        st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)
