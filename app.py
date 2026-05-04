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

# --- 0. 🚀 基礎工具函數 (公用區) ---
def get_realtime_price(stock_id):
    """即時價格抓取"""
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

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 戰情指揮中心", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# 初始化 session_state
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

# --- 3. 🛡️ 族群 CSV 讀取 (供兩個策略對齊產業資訊) ---
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
    indices = {"上市": ["TSE", "^TWII"], "上櫃": ["OTC", "^TWOII"]}
    for k, v in indices.items():
        try:
            curr_p = get_realtime_price(v[0])
            df_h = get_historical_data(v[1])
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                base_list = df_h['Close'].iloc[-20:-1].tolist() if df_h.index[-1].date() >= datetime.now().date() else df_h['Close'].iloc[-19:].tolist()
                c_list = base_list + [curr_p]
                m20 = sum(c_list)/20
                std_v = pd.Series(c_list).std()
                bw = (std_v * 4) / m20 if m20 != 0 else 0.0
                light = "🟢 綠燈" if curr_p > (sum(c_list[-5:])/5) else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
            else: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
        except: res[k] = {"燈號": "⚠️ 數據斷訊", "價格": 0.0, "帶寬": 0.0}
    return res
m_env = get_market_env()

# --- 5. 側邊欄模式切換 ---
st.sidebar.title("🛠️ 模式切換")
app_mode = st.sidebar.radio("選擇策略掃描", ["🏹 姊布林 ABCDE", "📈 營收動能策略"])

# =================================================================
# BLOCK A：🏹 姊布林 ABCDE 區塊 (完整保留原始邏輯)
# =================================================================
if app_mode == "🏹 姊布林 ABCDE":
    st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
    m_col1, m_col2 = st.columns(2)
    with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
    with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

    raw_input = st.sidebar.text_area("輸入股票代碼", height=150, key="boll_input")

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
                    current_env = m_env[m_type]
                    
                    if df.index[-1].date() >= datetime.now().date():
                        p_yest = float(df['Close'].iloc[-2])
                        history_for_ma = df['Close'].iloc[-20:-1].tolist()
                    else:
                        p_yest = float(df['Close'].iloc[-1])
                        history_for_ma = df['Close'].iloc[-19:].tolist()
                    
                    close_20 = history_for_ma + [p_curr]
                    m20_now = sum(close_20) / 20
                    std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2)
                    bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    chg = (p_curr - p_yest) / p_yest
                    vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000 
                    ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
                    
                    # 策略判定邏輯 (A-E)
                    res_tag = ""
                    if p_curr <= upper_now: res_tag = "⚪ 未站上軌"
                    elif m20_now <= (sum(history_for_ma)/20): res_tag = "⚪ 斜率負"
                    elif vol_amt < 5: res_tag = "⚪ 量不足"
                    else:
                        if "🔴 紅燈" in main_market_light:
                            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                            else: res_tag = "⚪ 大盤紅燈限AB"
                        else:
                            if "🟢 綠燈" in current_env['燈號']:
                                env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                                if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：共振】"
                                elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額】"
                                elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                                elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                                elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                            elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"

                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag if res_tag else "⚪ 參數不符",
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                        "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
        if results: st.session_state.scan_results = pd.DataFrame(results)

    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# =================================================================
# BLOCK B：📈 營收動能策略區塊 (全新獨立開發)
# =================================================================
elif app_mode == "📈 營收動能策略":
    st.markdown("### 📈 營收動能掃描器 (近三月平均年增 > 20%)")

    def process_revenue_logic():
        folder = "revenue_data"
        if not os.path.exists(folder): return pd.DataFrame()

        all_market_res = []
        # 分開處理上市(TWSE)與上櫃(TPEX)
        for m_prefix, m_label in [("TWSE_", "上市"), ("TPEX_", "上櫃")]:
            files = sorted(glob.glob(os.path.join(folder, f"{m_prefix}*.csv")), reverse=True)[:3]
            if len(files) < 3: continue
            
            dfs = []
            for f in files:
                try:
                    df = pd.read_csv(f, encoding='utf-8-sig')
                    # 強制清洗欄位名稱與提取
                    df.columns = [c.strip() for c in df.columns]
                    target_cols = ['公司代號', '公司名稱', '營業收入-去年同月增減(%)']
                    df = df[target_cols].copy()
                    df['公司代號'] = df['公司代號'].astype(str).str.strip()
                    df['營業收入-去年同月增減(%)'] = pd.to_numeric(df['營業收入-去年同月增減(%)'], errors='coerce').fillna(0)
                    dfs.append(df)
                except: continue
            
            if dfs:
                # 合併三個月資料並計算平均
                m_combined = pd.concat(dfs)
                m_avg = m_combined.groupby(['公司代號', '公司名稱'])['營業收入-去年同月增減(%)'].mean().reset_index()
                m_avg = m_avg[m_avg['營業收入-去年同月增減(%)'] > 20].copy()
                m_avg['市場別'] = m_label
                all_market_res.append(m_avg)
        
        return pd.concat(all_market_res) if all_market_res else pd.DataFrame()

    if st.sidebar.button("📊 執行營收分析"):
        with st.spinner("正在提取營收數據並進行即時比價..."):
            momentum_base = process_revenue_logic()
            final_rev_list = []
            
            if not momentum_base.empty:
                for _, row in momentum_base.iterrows():
                    code = row['公司代號']
                    # 即時行情抓取
                    p_curr = get_realtime_price(code)
                    if not p_curr: continue
                    
                    # 成交量與漲幅
                    suffix = ".TW" if row['市場別'] == "上市" else ".TWO"
                    df_h = get_historical_data(code + suffix)
                    chg_s, vol_a = "0.0%", 0.0
                    if not df_h.empty:
                        if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                        p_yest = df_h['Close'].iloc[-2] if len(df_h)>1 else df_h['Close'].iloc[-1]
                        chg_s = f"{((p_curr - p_yest) / p_yest) * 100:.1f}%"
                        vol_a = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                    
                    # 對齊根目錄產業資訊
                    info = stock_info_map.get(code, {"產業排位": "-", "族群細分": "-"})

                    final_rev_list.append({
                        "市場別": row['市場別'],
                        "代號": code,
                        "名稱": row['公司名稱'],
                        "近三月平均年增%": round(row['營業收入-去年同月增減(%)'], 2),
                        "現價": p_curr,
                        "漲幅%": chg_s,
                        "成交值(億)": round(vol_a, 1),
                        "產業排位": info["產業排位"],
                        "族群細分": info["族群細分"]
                    })
                st.session_state.revenue_results = pd.DataFrame(final_rev_list)
            else:
                st.warning("未找到符合條件(>20%)的營收個股，請檢查 revenue_data 資料夾。")

    if st.session_state.revenue_results is not None:
        # st.dataframe 原生支持點擊標題排序篩選
        st.dataframe(st.session_state.revenue_results, use_container_width=True, hide_index=True)

# --- 退出與清除 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.revenue_results = None
    st.rerun()
