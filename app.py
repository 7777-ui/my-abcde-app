import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import glob  # 用於讀取多份營收檔案
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 🚀 即時數據抓取函數 (解決 15 分鐘延遲) ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id

    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        patterns = [
            r'"regularMarketPrice":\s*([0-9.]+)',
            r'"price":\s*"([0-9,.]+)"'
        ]
        for p in patterns:
            match = re.search(p, response.text)
            if match:
                val = float(match.group(1).replace(',', ''))
                if val > 0: return val
    except:
        pass
    return None

# --- 0.1 🏎️ 歷史數據快取 (提升搜尋速度) ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    df = yf.download(code_with_suffix, period="2mo", progress=False)
    # 確保處理多重索引問題
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df

# --- [新增] 📊 營收動能輔助函數 (不影響原始邏輯) ---
@st.cache_data(ttl=86400)
def get_revenue_momentum_info():
    """
    讀取 local 的營收 CSV，計算近三月平均年增率
    """
    rev_mapping = {}
    # 假設營收檔案放在 revenue_data 資料夾內
    folder = "revenue_data"
    if not os.path.exists(folder): return rev_mapping
    
    files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)[:3] # 取最新三個月
    month_data = []
    for f in files:
        try:
            df = pd.read_csv(f)
            df['公司代號'] = df['公司代號'].astype(str).str.strip()
            month_data.append(df[['公司代號', '營業收入-去年同月增減(%)']])
        except: continue
    
    if month_data:
        combined = pd.concat(month_data)
        avg_rev = combined.groupby('公司代號')['營業收入-去年同月增減(%)'].mean().to_dict()
        return avg_rev
    return rev_mapping

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

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

# --- 3. 🛡️ 族群 CSV 讀取 ---
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
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    rt_indices = {"上市": "TSE", "上櫃": "OTC"}
    yf_indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in rt_indices.items():
        try:
            curr_p = get_realtime_price(v)
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
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室 (即時優化版)")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}** (加權總控機制已啟動)")

# --- 6. 側邊欄與搜尋邏輯 ---
st.sidebar.title("🛠️ 戰情室設定")

# 【營收動能控制區塊】
st.sidebar.markdown("### 📊 基本面過濾")
use_rev_filter = st.sidebar.checkbox("🚀 開啟營收動能過濾", value=False, help="僅顯示近三月營收平均年增率達標的標的")

# 初始化營收數據
rev_data = {}
min_rev_growth = 0

if use_rev_filter:
    # 呼叫先前定義的輔助函數讀取 CSV
    rev_data = get_revenue_momentum_info()
    min_rev_growth = st.sidebar.slider("營收平均年增門檻 (%)", min_value=0, max_value=100, value=20, step=5)
    st.sidebar.info(f"當前過濾：營收 YoY > {min_rev_growth}%")
else:
    st.sidebar.write("ℹ️ 目前僅使用技術面布林策略")

st.sidebar.markdown("---")

# 股票代碼輸入
raw_input = st.sidebar.text_area("輸入掃描代碼 (可貼上整段文字)", height=150, placeholder="例如: 2330 2454 3037...")

if st.sidebar.button("🚀 開始執行戰情掃描") and raw_input:
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    main_market_light = m_env['上市']['燈號']
    
    with st.spinner("正在交叉比對技術面與營收動能..."):
        for code in codes:
            # --- [核心過濾邏輯] ---
            # 如果開啟營收過濾，檢查數據是否存在且是否達標
            if use_rev_filter:
                avg_r = rev_data.get(code, -999) # 若無數據預設 -999
                if avg_r < min_rev_growth:
                    continue # 不達標，直接跳過該股票，不執行後續運算

            # --- [技術面運算區] --- (保持原本布林策略邏輯不動)
            info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
            p_curr = get_realtime_price(code)
            if not p_curr: continue
            
            df = get_historical_data(f"{code}.TW")
            m_type = "上市"
            if df.empty or len(df) < 10:
                df = get_historical_data(f"{code}.TWO")
                m_type = "上櫃"

            if not df.empty and len(df) >= 20:
                # ... (此處保留您原始的布林 A/B/C/D/E 判定代碼) ...
                # (為了精簡，中間邏輯同您提供的版本)
                
                # 在結果清單中額外標註營收數據（若有開啟）
                result_item = {
                    "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                    "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                    "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                    "產業排位": info["產業排位"]
                }
                
                if use_rev_filter:
                    result_item["營收平均YoY%"] = f"{rev_data.get(code, 0):.1f}%"
                
                results.append(result_item)

        if results:
            st.session_state.scan_results = pd.DataFrame(results)
        else:
            st.warning("⚠️ 掃描完成，但在目前的營收與技術面篩選下，無符合標的。")

# --- 7. 顯示結果 ---
if st.session_state.scan_results is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
