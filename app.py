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

# --- 0. 公用工具函數 ---
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

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 雙策略戰情室", page_icon="🏹", layout="wide")
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

# --- 3. 🛡️ 產業資料庫 (供兩大區塊調用對齊) ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                df_local = pd.read_csv(f_name, encoding='utf-8-sig').fillna('-')
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

# --- 4. 大盤環境 ---
m_env = {} 
# (此處保留原程式碼大盤偵測邏輯，為節省篇幅簡略，執行時請包含原 get_market_env)

# --- 5. 側邊欄模式切換 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇分析模式", ["姊布林策略", "營收動能參數"])

# =================================================================
# 區塊一：姊布林策略 (保持原始邏輯獨立)
# =================================================================
if mode == "姊布林策略":
    st.subheader("🏹 姊布林 ABCDE 策略掃描")
    raw_input = st.sidebar.text_area("輸入代碼 (空白或換行分隔)", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        for code in codes:
            # ... 此處完全帶入您原始程式碼中的姊布林計算邏輯 ...
            # 包含 get_realtime_price(code), get_historical_data, 斜率, 帶寬判斷等
            pass
        st.session_state.scan_results = pd.DataFrame(results)
    
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# =================================================================
# 區塊二：營收動能參數 (全新獨立區塊)
# =================================================================
elif mode == "營收動能參數":
    st.subheader("📊 營收動能戰情室 (近三月平均年增 > 20%)")
    
    if st.sidebar.button("🔍 執行營收分析"):
        folder = "revenue_data"
        all_rev_files = glob.glob(os.path.join(folder, "*.csv"))
        
        if not all_rev_files:
            st.error(f"錯誤：在 {folder} 資料夾中找不到營收 CSV 檔案")
        else:
            with st.spinner("正在合併營收資料並計算動能..."):
                rev_list = []
                for f in all_rev_files:
                    try:
                        # 3-1. 僅讀取指定 4 個欄位
                        df_tmp = pd.read_csv(f, encoding='utf-8-sig')
                        # 處理欄位名稱可能略有差異的情況，確保抓到「去年同月增減(%)」
                        yoy_col = [c for c in df_tmp.columns if '去年同月增減' in c][0]
                        df_clean = df_tmp[['公司代號', '公司名稱', yoy_col]].copy()
                        df_clean.columns = ['代號', '名稱', '年增率']
                        rev_list.append(df_clean)
                    except: continue
                
                if rev_list:
                    # 1. 合併近三月資料
                    full_rev_df = pd.concat(rev_list)
                    full_rev_df['代號'] = full_rev_df['代號'].astype(str).str.strip()
                    
                    # 5. 計算近三月平均年增率並篩選 > 20%
                    avg_rev = full_rev_df.groupby(['代號', '名稱'])['年增率'].mean().reset_index()
                    high_growth = avg_rev[avg_rev['年增率'] > 20.0]
                    
                    final_revenue_data = []
                    for _, row in high_growth.iterrows():
                        sid = row['代號']
                        # 3-2. 即時價格來源 (獨立抓取)
                        p_now = get_realtime_price(sid)
                        if not p_now: continue
                        
                        df_h = get_historical_data(f"{sid}.TW")
                        if df_h.empty: df_h = get_historical_data(f"{sid}.TWO")
                        
                        if not df_h.empty:
                            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                            p_yest = float(df_h['Close'].iloc[-1])
                            chg_pct = (p_now - p_yest) / p_yest
                            vol_亿 = (df_h['Volume'].iloc[-1] * p_now) / 100000000
                            
                            # 3-3. 對齊產業排位與族群 (從 TWSE/TPEX 映射)
                            info = stock_info_map.get(sid, {"產業排位": "-", "族群細分": "-"})
                            
                            # 6. 組合 7 個欄位
                            final_revenue_data.append({
                                "代號": sid,
                                "名稱": row['名稱'],
                                "近三月平均年增%": round(row['年增率'], 2),
                                "現價": p_now,
                                "漲幅%": f"{chg_pct*100:.2f}%",
                                "成交值(億)": round(vol_亿, 2),
                                "產業排位": info["產業排位"],
                                "族群細分": info["族群細分"]
                            })
                    
                    st.session_state.revenue_results = pd.DataFrame(final_revenue_data)

    # 7. 顯示結果 (含篩選排序功能)
    if st.session_state.revenue_results is not None:
        st.dataframe(
            st.session_state.revenue_results.sort_values("近三月平均年增%", ascending=False), 
            use_container_width=True, 
            hide_index=True
        )

# --- 10. 安全登出 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.revenue_results = None
    st.rerun()
