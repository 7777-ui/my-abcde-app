import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 🚀 即時數據抓取函數 ---
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

# --- 📂 營收檔案讀取 (支援中英文資料夾) ---
def get_local_revenue_safe(year_month):
    possible_folders = ["revenue_data"]
    dfs = []
    for folder in possible_folders:
        for prefix in ["TWSE", "TPEX"]:
            file_path = os.path.join(os.getcwd(), folder, f"{prefix}_{year_month}.csv")
            if os.path.exists(file_path):
                try:
                    try: df_l = pd.read_csv(file_path, encoding='utf-8-sig')
                    except: df_l = pd.read_csv(file_path, encoding='cp950')
                    df_l.columns = [str(c).strip() for c in df_l.columns]
                    col = [c for c in df_l.columns if '去年同月增減' in c]
                    if col:
                        dfs.append(df_l[['公司代號', '公司名稱', col[0]]].rename(columns={col[0]: '年增%'}))
                except: pass
    return pd.concat(dfs).drop_duplicates(subset=['公司代號']) if dfs else pd.DataFrame()

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "rev_results" not in st.session_state: st.session_state.rev_results = None

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f: b64_encoded = base64.b64encode(f.read()).decode()
    st.markdown(f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    </style>
    """, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": st.session_state.password_correct = True; st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 3. 🛡️ 族群資料 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                try: df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df_local = pd.read_csv(f_name, encoding='cp950')
                for _, row in df_local.fillna('-').iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-", "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-", "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-", "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 大盤環境 ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    idx_map = {"上市": ("TSE", "^TWII"), "上櫃": ("OTC", "^TWOII")}
    for k, (rt_id, yf_id) in idx_map.items():
        try:
            curr_p = get_realtime_price(rt_id)
            df_h = get_historical_data(yf_id)
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                c_list = df_h['Close'].iloc[-19:].tolist() + [curr_p]
                m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
                bw = (pd.Series(c_list).std() * 4) / m20 if m20 != 0 else 0.0
                light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
            else: res[k] = {"燈號": "⚠️ 斷訊", "價格": 0.0, "帶寬": 0.0}
        except: res[k] = {"燈號": "⚠️ 錯誤", "價格": 0.0, "帶寬": 0.0}
    return res
m_env = get_market_env()

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
c1, c2 = st.columns(2)
# 修正 SyntaxError: 這裡不要換行
c1.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
c2.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 6. 側邊欄 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇模式", ["🏹 姊布林個股掃描", "📈 營收動能 (三月平均 > 20%)"])

if mode == "🏹 姊布林個股掃描":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("掃描中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                df = get_historical_data(f"{code}.TW")
                m_type = "上市"
                if df.empty or len(df) < 10: df = get_historical_data(f"{code}.TWO"); m_type = "上櫃"
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    cur_env = m_env[m_type]
                    p_yest = float(df['Close'].iloc[-1])
                    hist = df['Close'].iloc[-19:].tolist()
                    c20 = hist + [p_curr]
                    m20 = sum(c20)/20; std = pd.Series(c20).std()
                    bw = (std*4)/m20 if m20 != 0 else 0.0
                    chg = (p_curr - p_yest)/p_yest
                    
                    res_tag = "⚪ 觀察中"
                    if p_curr > m20 + (std*2) and m20 > sum(hist)/20:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                        elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                    
                    results.append({"代號": code, "名稱": info["簡稱"], "策略": res_tag, "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "帶寬%": f"{bw*100:.1f}%", "產業排位": info["產業排位"], "族群": info["族群細分"]})
        st.session_state.scan_results = pd.DataFrame(results)
    if st.session_state.scan_results is not None: st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif mode == "📈 營收動能 (三月平均 > 20%)":
    if st.sidebar.button("🔍 執行營收全自動篩選"):
        yms = ["202603", "202602", "202601"]
        with st.spinner("檔案讀取中..."):
            r_list = [get_local_revenue_safe(ym) for ym in yms]
            if len([d for d in r_list if not d.empty]) == 3:
                merged = r_list[0].rename(columns={'年增%': 'm1'})
                merged = pd.merge(merged, r_list[1][['公司代號', '年增%']].rename(columns={'年增%': 'm2'}), on='公司代號')
                merged = pd.merge(merged, r_list[2][['公司代號', '年增%']].rename(columns={'年增%': 'm3'}), on='公司代號')
                merged['平均年增%'] = merged[['m1', 'm2', 'm3']].mean(axis=1)
                winners = merged[merged['平均年增%'] > 20.0].sort_values('平均年增%', ascending=False).head(50)
                
                final = []
                for _, r in winners.iterrows():
                    cid = str(r['公司代號']).strip()
                    cp = get_realtime_price(cid)
                    if cp: final.append({"代號": cid, "名稱": r['公司名稱'], "平均年增%": f"{r['平均年增%']:.1f}%", "現價": cp})
                st.session_state.rev_results = pd.DataFrame(final)
            else:
                st.error("❌ 檔案不足！請檢查 GitHub 上的『revenue_data』資料夾是否包含 202601~03 的檔案。")
    if st.session_state.rev_results is not None: st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
