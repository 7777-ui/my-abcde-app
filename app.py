import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 1. 🏎️ 核心快取與數據抓取 (🛠️ /optimize: 快取機制) ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    """快取歷史數據，減少對 Yahoo Finance 的頻繁請求"""
    return yf.download(code_with_suffix, period="3mo", progress=False)

def get_realtime_price(stock_id):
    """即時價格抓取，包含大盤與個股"""
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
                return val if val > 0 else None
    except: pass
    return None

# --- 2. 🛡️ 資料庫預過濾 (🛠️ /scaffold: 預過濾邏輯) ---
@st.cache_data(ttl=604800)
def load_stock_database():
    """載入 CSV 並標註市場別，確保欄位對齊"""
    mapping = {}
    # 定義檔案與市場的對應
    market_files = {"TWSE.csv": "上市", "TPEX.csv": "上櫃"}
    for f_name, m_type in market_files.items():
        if os.path.exists(f_name):
            try:
                # 嘗試多種編碼讀取
                for enc in ['utf-8-sig', 'cp950']:
                    try:
                        df_local = pd.read_csv(f_name, encoding=enc).fillna('-')
                        break
                    except: continue
                
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "名稱": str(row.iloc[1]).strip(),
                            "市場": m_type,
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping

# --- 3. UI 與環境初始化 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

def set_bg(image_file):
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        st.markdown(f"""
            <style>
            .stApp {{ background-image: url("data:image/jpeg;base64,{b64}"); background-size: cover; background-attachment: fixed; }}
            .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.75); z-index: -1; }}
            </style>
        """, unsafe_allow_html=True)

set_bg("header_image.png")

# --- 4. 🔐 登入邏輯 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    pwd = st.text_input("🔑 密碼", type="password")
    if st.button("登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
    st.stop()

# --- 5. 📉 計算改進邏輯 (🛠️ /explain_math: 帶寬與均線) ---
def get_signals():
    """計算大盤燈號與帶寬"""
    res = {}
    for label, code, yf_c in [("上市", "TSE", "^TWII"), ("上櫃", "OTC", "^TWOII")]:
        p = get_realtime_price(code)
        df = get_historical_data(yf_c)
        if not df.empty and p:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            # 取得前 19 日收盤價 + 今日即時價 = 完整 20 日序列
            closes = df['Close'].dropna().iloc[-19:].tolist() + [p]
            m20 = sum(closes) / 20
            std = pd.Series(closes).std()
            bw = (std * 4) / m20
            light = "🟢 綠燈" if p > (sum(closes[-5:])/5) else ("🟡 黃燈" if p > m20 else "🔴 紅燈")
            res[label] = {"燈號": light, "價格": p, "帶寬": bw}
    return res

stock_db = load_stock_database()
m_env = get_signals()

# --- 6. 主介面 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

mode = st.sidebar.radio("🔭 選擇模式", ["姊布林 ABCDE", "營收動能策略"])

# --- 7. 姊布林 ABCDE (🛠️ /optimize: 欄位加上市場別) ---
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("代碼輸入", height=150)
    if st.sidebar.button("啟動掃描") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        final_data = []
        for c in codes:
            meta = stock_db.get(c, {"名稱": f"台股{c}", "市場": "未知", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
            p_now = get_realtime_price(c)
            if not p_now: continue
            
            # 自動判定市場字尾
            suffix = ".TW" if meta["市場"] == "上市" else ".TWO"
            df = get_historical_data(c + suffix)
            if df.empty: # 二次嘗試
                suffix = ".TWO" if suffix == ".TW" else ".TW"
                df = get_historical_data(c + suffix)
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                # 計算邏輯改進：包含今日現價的布林帶
                hist_19 = df['Close'].dropna().iloc[-19:].tolist()
                c20 = hist_19 + [p_now]
                m20 = sum(c20)/20
                std = pd.Series(c20).std()
                bw = (std * 4) / m20
                vol_amt = (df['Volume'].iloc[-1] * p_now) / 100000000
                
                tag = "⚪ 觀察"
                if p_now > (m20 + 2*std) and m20 > (sum(hist_19)/19) and vol_amt > 5:
                    if 0.05 <= bw <= 0.2: tag = "🎯 核心標的"
                    elif bw > 0.2: tag = "🌊 瘋狗標的"
                
                final_data.append({
                    "市場": meta["市場"], "代號": c, "名稱": meta["名稱"], "策略標籤": tag,
                    "現價": p_now, "成交值(億)": round(vol_amt, 1), "個股帶寬%": f"{bw*100:.1f}%",
                    "產業排位": meta["產業排位"], "族群細分": meta["族群細分"]
                })
        st.session_state.scan_results = pd.DataFrame(final_data)

# --- 8. 營收動能 (🛠️ /debug: 修復編碼報錯) ---
elif mode == "營收動能策略":
    if st.sidebar.button("📊 分析營收"):
        files = sorted(glob.glob("revenue_data/*.csv"), key=os.path.getmtime, reverse=True)[:3]
        if len(files) < 3: st.warning("需要 3 個月營收 CSV")
        else:
            dfs = []
            for f in files:
                tdf = None
                for enc in ['utf-8-sig', 'cp950', 'big5']:
                    try: 
                        tdf = pd.read_csv(f, encoding=enc, errors='ignore')
                        break
                    except: continue
                if tdf is not None:
                    tdf.columns = [str(x).strip() for x in tdf.columns]
                    tdf['公司代號'] = tdf['公司代號'].astype(str).str.strip()
                    tdf['營業收入-當月營收'] = pd.to_numeric(tdf['營業收入-當月營收'].astype(str).str.replace(',',''), errors='coerce')
                    dfs.append(tdf[['公司代號', '公司名稱', '營業收入-當月營收']].dropna())
            
            # 計算平均成長
            m = dfs[0].merge(dfs[1], on='公司代號', suffixes=('', '_2')).merge(dfs[2], on='公司代號', suffixes=('', '_3'))
            m['avg_g'] = ((m.iloc[:,2]-m.iloc[:,4])/m.iloc[:,4] + (m.iloc[:,4]-m.iloc[:,5])/m.iloc[:,5]) / 2 * 100
            
            res_list = []
            for _, row in m[m['avg_g'] > 20].iterrows():
                c = row['公司代號']
                meta = stock_db.get(c, {"市場": "未知", "產業排位": "-", "族群細分": "-"})
                p = get_realtime_price(c)
                if p:
                    res_list.append({
                        "市場": meta["市場"], "代號": c, "名稱": row['公司名稱'], 
                        "平均成長%": f"{row['avg_g']:.1f}%", "現價": p,
                        "產業排位": meta["產業排位"], "族群細分": meta["族群細分"]
                    })
            st.session_state.scan_results = pd.DataFrame(res_list)

# --- 9. 顯示結果 ---
if st.session_state.get("scan_results") is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
