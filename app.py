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

# --- 0. 🚀 即時數據抓取函數 (保留原始邏輯) ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id

    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 額外抓取昨收價以計算漲跌幅
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        y_match = re.search(r'"regularMarketPreviousClose":\s*([0-9.]+)', response.text)
        v_match = re.search(r'"regularMarketVolume":\s*([0-9.]+)', response.text)
        
        price = float(p_match.group(1)) if p_match else None
        yest = float(y_match.group(1)) if y_match else None
        vol = float(v_match.group(1)) if v_match else 0
        return price, yest, vol
    except:
        return None, None, 0

# --- 0.1 🏎️ 歷史數據快取 ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "revenue_results" not in st.session_state: st.session_state.revenue_results = None

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f:
            b64_encoded = base64.b64encode(f.read()).decode()
    style = f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; padding: 5px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 3. 🛡️ 族群 CSV 讀取 (供兩個模式共用) ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    files = ["TWSE.csv", "TPEX.csv"] 
    for f_name in files:
        if os.path.exists(f_name):
            try:
                try: df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df_local = pd.read_csv(f_name, encoding='cp950')
                df_local = df_local.fillna('-')
                for _, row in df_local.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 大盤環境偵測 (保留原始邏輯) ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    rt_indices = {"上市": "TSE", "上櫃": "OTC"}
    yf_indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in rt_indices.items():
        try:
            curr_p, _, _ = get_realtime_price(v)
            df_h = get_historical_data(yf_indices[k])
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                base_list = df_h['Close'].iloc[-20:-1].tolist() if df_h.index[-1].date() >= datetime.now().date() else df_h['Close'].iloc[-19:].tolist()
                c_list = base_list + [curr_p]
                m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
                std_v = pd.Series(c_list).std()
                bw = (std_v * 4) / m20 if m20 != 0 else 0.0
                light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
            else: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
        except: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
    return res

m_env = get_market_env()

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 6. 側邊欄切換模式 ---
st.sidebar.title("🛠️ 模式切換")
app_mode = st.sidebar.radio("選擇掃描模式", ["姊布林 ABCDE", "營收動能參數"])

if app_mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        with st.spinner("姊布林分析中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "族群細分": "-"})
                p_curr, p_yest, vol_raw = get_realtime_price(code)
                if not p_curr: continue
                df = get_historical_data(f"{code}.TW")
                m_type = "上市"
                if df.empty or len(df) < 10:
                    df = get_historical_data(f"{code}.TWO")
                    m_type = "上櫃"
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    current_env = m_env[m_type]
                    # ... (中間姊布林判定邏輯完全保留) ...
                    p_target_yest = float(df['Close'].iloc[-2]) if df.index[-1].date() >= datetime.now().date() else float(df['Close'].iloc[-1])
                    chg = (p_curr - p_target_yest) / p_target_yest
                    vol_amt = (vol_raw * p_curr) / 100000000 
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "現價": p_curr, "漲跌幅%": f"{chg*100:.1f}%",
                        "成交值(億)": round(vol_amt, 1), "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
        st.session_state.scan_results = pd.DataFrame(results)
    
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif app_mode == "營收動能參數":
    st.sidebar.info("營收動能模式：抓取近三月平均年增率 > 20% 個股")
    if st.sidebar.button("📊 執行營收動能篩選"):
        # 設定搜尋月份 (請根據現有檔案修改月份)
        target_yms = ["202603", "202602", "202601"] 
        rev_data_list = []
        
        with st.spinner("讀取營收資料中..."):
            # 讀取三個月份的上市與上櫃資料
            all_codes = set()
            rev_map = {} # {code: [rev1, rev2, rev3]}

            for i, ym in enumerate(target_yms):
                for prefix in ["TWSE", "TPEX"]:
                    f_path = f"revenue_data/{prefix}_{ym}.csv"
                    if os.path.exists(f_path):
                        try:
                            try: df_rev = pd.read_csv(f_path, encoding='utf-8-sig')
                            except: df_rev = pd.read_csv(f_path, encoding='cp950')
                            
                            # 找出公司代號與年增率欄位 (假設年增率欄位標題包含"去年同月增減")
                            code_col = df_rev.columns[0] 
                            growth_col = [c for c in df_rev.columns if '去年同月增減' in str(c) and '%' in str(c)]
                            if growth_col:
                                for _, r in df_rev.iterrows():
                                    c_id = str(r[code_col]).strip()
                                    val = float(r[growth_col[0]])
                                    if c_id not in rev_map: rev_map[c_id] = [0.0, 0.0, 0.0]
                                    rev_map[c_id][i] = val
                                    all_codes.add(c_id)
                        except: pass

            final_rev_list = []
            for c_id in all_codes:
                avg_growth = sum(rev_map[c_id]) / 3
                if avg_growth > 20.0:
                    info = stock_info_map.get(c_id, {"簡稱": "-", "產業排位": "-", "族群細分": "-"})
                    p_curr, p_yest, vol_raw = get_realtime_price(c_id)
                    if p_curr:
                        chg = (p_curr - p_yest) / p_yest if p_yest else 0
                        vol_amt = (vol_raw * p_curr) / 100000000
                        final_rev_list.append({
                            "代號": c_id, "名稱": info["簡稱"], 
                            "近三月平均年增率>20%": f"{avg_growth:.2f}%",
                            "現價": p_curr, "漲跌幅%": f"{chg*100:.2f}%",
                            "成交值(億)": round(vol_amt, 2),
                            "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                        })
            st.session_state.revenue_results = pd.DataFrame(final_rev_list)

    if st.session_state.revenue_results is not None:
        # st.dataframe 預設即提供點擊標題排序與篩選功能
        st.dataframe(st.session_state.revenue_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
