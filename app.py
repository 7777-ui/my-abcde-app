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

# --- 1. 核心快取機制 ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    """快取歷史數據，減少重複請求"""
    return yf.download(code_with_suffix, period="3mo", progress=False)

@st.cache_data(ttl=60)
def get_realtime_price(stock_id):
    """抓取即時價格，包含重試邏輯"""
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

# --- 2. 數據庫與環境初始化 ---
@st.cache_data(ttl=604800)
def load_stock_database():
    """預過濾並載入 CSV 資料庫，確保欄位對齊"""
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                # 處理編碼與空白
                df_local = pd.read_csv(f_name, encoding='utf-8-sig').fillna('-')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "名稱": str(row.iloc[1]).strip(),
                            "市場": "上市" if f_name == "TWSE.csv" else "上櫃",
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping

# --- 3. UI 設定 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

def apply_custom_ui(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    st.markdown(f"""
        <style>
        .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-size: cover; background-attachment: fixed; }}
        .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
        </style>
    """, unsafe_allow_html=True)

apply_custom_ui("header_image.png")

# --- 4. 登入邏輯 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    pwd = st.text_input("🔑 請輸入通關密語", type="password")
    if st.button("登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("❌ 拒絕存取")
    st.stop()

# --- 5. 燈號計算邏輯 ---
def fetch_market_signals():
    signals = {}
    for label, code, yf_code in [("上市", "TSE", "^TWII"), ("上櫃", "OTC", "^TWOII")]:
        p = get_realtime_price(code)
        df = get_historical_data(yf_code)
        if not df.empty and p:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            hist = df['Close'].dropna().iloc[-19:].tolist()
            full_20 = hist + [p]
            m5, m20 = sum(full_20[-5:])/5, sum(full_20)/20
            bw = (pd.Series(full_20).std() * 4) / m20
            light = "🟢 綠燈" if p > m5 else ("🟡 黃燈" if p > m20 else "🔴 紅燈")
            signals[label] = {"燈號": light, "價格": p, "帶寬": bw}
        else: signals[label] = {"燈號": "⚠️ 斷訊", "價格": 0, "帶寬": 0}
    return signals

stock_db = load_stock_database()
m_env = fetch_market_signals()

# --- 6. 介面與模式切換 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
c1, c2 = st.columns(2)
with c1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with c2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

mode = st.sidebar.radio("🔭 掃描模式", ["姊布林 ABCDE", "營收動能策略"])

# --- 7. 姊布林 ABCDE (改進計算與欄位) ---
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入代碼", height=150)
    if st.sidebar.button("🚀 執行掃描") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        final_list = []
        for c in codes:
            # 優先從資料庫抓名稱，抓不到再給預設
            meta = stock_db.get(c, {"名稱": f"台股{c}", "市場": "未知", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
            p_now = get_realtime_price(c)
            if not p_now: continue
            
            # 自動偵測市場別進行回測計算
            suffix = ".TW" if meta["市場"] == "上市" else ".TWO"
            df = get_historical_data(c + suffix)
            if df.empty: # 二次嘗試
                suffix = ".TWO" if suffix == ".TW" else ".TW"
                df = get_historical_data(c + suffix)
            
            if not df.empty and len(df) >= 20:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                df_c = df['Close'].dropna()
                p_yest = df_c.iloc[-1]
                hist_19 = df_c.iloc[-19:].tolist()
                c20 = hist_19 + [p_now]
                m20 = sum(c20)/20
                std = pd.Series(c20).std()
                bw = (std * 4) / m20
                chg = (p_now - p_yest) / p_yest
                vol_amt = (df['Volume'].iloc[-1] * p_now) / 100000000
                
                # 簡化標籤邏輯
                tag = "⚪ 觀察"
                if p_now > (m20 + 2*std) and m20 > (sum(hist_19)/19) and vol_amt > 5:
                    if 0.05 <= bw <= 0.1: tag = "🔥【A：潛龍】"
                    elif 0.1 < bw <= 0.2: tag = "🎯【B：海龍】"
                    elif 0.2 < bw: tag = "🌊【C：瘋狗】"

                final_list.append({
                    "市場": meta["市場"], "代號": c, "名稱": meta["名稱"], "策略標籤": tag,
                    "現價": p_now, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                    "個股帶寬%": f"{bw*100:.1f}%", "產業排位": meta["產業排位"], "實力指標": meta["實力指標"],
                    "族群細分": meta["族群細分"]
                })
        st.session_state.scan_results = pd.DataFrame(final_list)

# --- 8. 營收動能 (加上市場別與優化) ---
elif mode == "營收動能策略":
    if st.sidebar.button("📊 分析最新營收"):
        files = sorted(glob.glob("revenue_data/*.csv"), key=os.path.getmtime, reverse=True)[:3]
        if len(files) < 3: st.warning("需要 3 個月份的 CSV 檔案")
        else:
            dfs = []
            for f in files:
                tdf = pd.read_csv(f, encoding='utf-8-sig') if 'utf-8' in f else pd.read_csv(f, encoding='cp950')
                tdf.columns = [x.strip() for x in tdf.columns]
                dfs.append(tdf[['公司代號', '公司名稱', '營業收入-當月營收']].drop_duplicates('公司代號'))
            
            # 合併與計算
            m = dfs[0].merge(dfs[1], on='公司代號', suffixes=('', '_2')).merge(dfs[2], on='公司代號', suffixes=('', '_3'))
            m['avg_g'] = ((m.iloc[:,2]-m.iloc[:,4])/m.iloc[:,4] + (m.iloc[:,4]-m.iloc[:,5])/m.iloc[:,5]) / 2 * 100
            
            results = []
            for _, row in m[m['avg_g'] > 20].iterrows():
                c = str(row['公司代號']).strip()
                meta = stock_db.get(c, {"市場": "未知", "產業排位": "-", "族群細分": "-"})
                p = get_realtime_price(c)
                if p:
                    results.append({
                        "市場": meta["市場"], "代號": c, "名稱": row['公司名稱'], 
                        "平均營收增長": f"{row['avg_g']:.1f}%", "現價": p,
                        "產業排位": meta["產業排位"], "族群細分": meta["族群細分"]
                    })
            st.session_state.scan_results = pd.DataFrame(results)

# --- 9. 顯示結果 ---
if st.session_state.get("scan_results") is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)
