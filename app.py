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

# --- 0. 原始公用函數 (保留基底) ---
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
st.set_page_config(page_title="🏹 姊布林ABCDE & 營收戰情室", page_icon="🏹", layout="wide")
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

# --- 3. 🛡️ 族群 CSV 讀取 (公用映射庫) ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
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

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    for k, v in {"上市": "TSE", "上櫃": "OTC"}.items():
        curr_p = get_realtime_price(v)
        df_h = get_historical_data("^TWII" if k == "上市" else "^TWOII")
        if not df_h.empty and curr_p:
            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
            df_h = df_h.dropna(subset=['Close'])
            base_list = df_h['Close'].iloc[-19:].tolist()
            c_list = base_list + [curr_p]
            m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
            std_v = pd.Series(c_list).std()
            bw = (std_v * 4) / m20 if m20 != 0 else 0.0
            light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
            res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
        else: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
    return res
m_env = get_market_env()

# --- 5. 側邊欄切換 ---
st.sidebar.title("🛠️ 設定區")
mode = st.sidebar.radio("切換模式", ["姊布林策略", "營收動能參數"])

# =================================================================
# 區塊 A：姊布林策略 (完全保留原始邏輯)
# =================================================================
if mode == "姊布林策略":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        
        with st.spinner("姊布林分析中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "族群細分": "-"})
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                df = get_historical_data(f"{code}.TW")
                m_type = "上市"
                if df.empty or len(df) < 10:
                    df = get_historical_data(f"{code}.TWO")
                    m_type = "上櫃"

                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    p_yest = float(df['Close'].iloc[-1])
                    history_for_ma = df['Close'].iloc[-19:].tolist()
                    close_20 = history_for_ma + [p_curr]
                    m20_now = sum(close_20) / 20
                    std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2)
                    bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    chg = (p_curr - p_yest) / p_yest
                    vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000 
                    
                    res_tag = ""
                    fail_reasons = []
                    if p_curr <= upper_now: fail_reasons.append("未站上軌")
                    if m20_now <= sum(df['Close'].iloc[-20:-1]) / 20: fail_reasons.append("斜率負")
                    if vol_amt < 5: fail_reasons.append("量不足")

                    if not fail_reasons:
                        if "🔴 紅燈" in main_market_light:
                            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        else:
                            c_env = m_env[m_type]
                            ratio = bw / c_env['帶寬'] if c_env['帶寬'] > 0 else 0
                            if "🟢 綠燈" in c_env['燈號']:
                                env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                                if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：共振】"
                                elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額】"
                                elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                                elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                                elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                    
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag if res_tag else "⚪ 條件不符",
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
        st.session_state.scan_results = pd.DataFrame(results)

    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# =================================================================
# 區塊 B：營收動能參數 (獨立邏輯，對齊代號後抓即時價與產業排位)
# =================================================================
elif mode == "營收動能參數":
    if st.sidebar.button("📊 執行營收動能篩選"):
        folder = "revenue_data"
        all_rev_files = glob.glob(os.path.join(folder, "*.csv"))
        
        if not all_rev_files:
            st.error(f"錯誤：在 {folder} 資料夾中找不到營收 CSV 檔案")
        else:
            with st.spinner("營收數據計算中..."):
                rev_frames = []
                for f in all_rev_files:
                    try:
                        # 僅讀取指定欄位：資料年月、公司代號、公司名稱、營業收入-去年同月增減(%)
                        df_tmp = pd.read_csv(f, encoding='utf-8-sig')
                        # 自動尋找包含年增率的欄位
                        yoy_col = [c for c in df_tmp.columns if '去年同月增減(%)' in c][0]
                        df_target = df_tmp[['公司代號', '公司名稱', yoy_col]].copy()
                        df_target.columns = ['代號', '名稱', '年增率']
                        rev_frames.append(df_target)
                    except: pass
                
                if rev_frames:
                    all_rev_df = pd.concat(rev_frames)
                    all_rev_df['代號'] = all_rev_df['代號'].astype(str).str.strip()
                    # 計算近三月平均
                    avg_growth = all_rev_df.groupby(['代號', '名稱'])['年增率'].mean().reset_index()
                    # 篩選 > 20%
                    high_growth = avg_growth[avg_growth['年增率'] > 20.0].copy()
                    
                    revenue_final = []
                    for _, row in high_growth.iterrows():
                        c_id = row['代號']
                        # 1. 抓取即時價格與漲幅 (與姊布林相同來源但獨立寫)
                        p_now = get_realtime_price(c_id)
                        if not p_now: continue
                        
                        # 2. 抓取歷史數據計算昨收漲幅與成交值
                        df_h = get_historical_data(f"{c_id}.TW")
                        if df_h.empty: df_h = get_historical_data(f"{c_id}.TWO")
                        
                        if not df_h.empty:
                            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                            p_yest = float(df_h['Close'].iloc[-1])
                            v_amt = (df_h['Volume'].iloc[-1] * p_now) / 100000000
                            chg_pct = (p_now - p_yest) / p_yest
                            
                            # 3. 對齊產業排位 (從 TWSE.csv / TPEX.csv 映射)
                            info = stock_info_map.get(c_id, {"產業排位": "-", "族群細分": "-"})
                            
                            revenue_final.append({
                                "代號": c_id, "名稱": row['名稱'], 
                                "近三月平均年增%": round(row['年增率'], 2),
                                "現價": p_now, "漲幅%": f"{chg_pct*100:.2f}%", 
                                "成交值(億)": round(v_amt, 2),
                                "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                            })
                    
                    st.session_state.revenue_results = pd.DataFrame(revenue_final)

    if st.session_state.revenue_results is not None:
        st.dataframe(st.session_state.revenue_results.sort_values("近三月平均年增%", ascending=False), 
                     use_container_width=True, hide_index=True)

# --- 7. 安全登出 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.revenue_results = None
    st.rerun()
