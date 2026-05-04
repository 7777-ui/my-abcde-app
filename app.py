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

# --- 0.1 歷史數據快取 ---
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

# ============================================================================
# 【區塊 A：營收動能策略 - 強化邏輯版】
# ============================================================================

def clean_yoy_value(val):
    """強化數值清洗，處理百分比符號與非數值"""
    if pd.isna(val) or val == '-': return 0.0
    try:
        return float(str(val).replace('%', '').replace(',', '').strip())
    except: return 0.0

@st.cache_data(ttl=3600)
def get_revenue_data_cleaned(market_prefix="TWSE_"):
    """讀取最新 3 個月營收 CSV 並清洗"""
    if not os.path.exists("revenue_data"): return pd.DataFrame()
    
    files = sorted([f for f in os.listdir("revenue_data") if f.startswith(market_prefix) and f.endswith(".csv")], reverse=True)[:3]
    revenue_list = []
    
    for f in files:
        f_path = os.path.join("revenue_data", f)
        try:
            try: df = pd.read_csv(f_path, encoding='utf-8-sig')
            except: df = pd.read_csv(f_path, encoding='cp950')
            
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # 靈活比對營收年增率欄位
            yoy_col = next((c for c in df.columns if "去年同月" in c and "增減" in c), None)
            id_col = next((c for c in df.columns if "公司代號" in c or "代號" in c), None)
            name_col = next((c for c in df.columns if "公司名稱" in c or "名稱" in c), None)
            
            if yoy_col and id_col:
                df_sub = df[[id_col, name_col, yoy_col]].copy()
                df_sub.columns = ['代號', '名稱', 'YoY']
                df_sub['代號'] = df_sub['代號'].astype(str).str.strip()
                df_sub['YoY'] = df_sub['YoY'].apply(clean_yoy_value)
                revenue_list.append(df_sub)
        except: pass
    return pd.concat(revenue_list) if revenue_list else pd.DataFrame()

def build_revenue_momentum_results():
    """執行營收動能掃描與數據補全"""
    with st.spinner("🔍 正在計算近三月營收動能 (YoY算術平均 > 20%)..."):
        df_twse = get_revenue_data_cleaned("TWSE_")
        df_tpex = get_revenue_data_cleaned("TPEX_")
        
        if df_twse.empty and df_tpex.empty: return pd.DataFrame()
        
        if not df_twse.empty: df_twse.insert(0, '市場別', '上市')
        if not df_tpex.empty: df_tpex.insert(0, '市場別', '上櫃')
        
        df_all = pd.concat([df_twse, df_tpex])
        # 計算算術平均
        df_agg = df_all.groupby(['市場別', '代號', '名稱'])['YoY'].mean().reset_index()
        df_agg = df_agg[df_agg['YoY'] > 20].copy()
        
        results = []
        for _, row in df_agg.iterrows():
            code = row['代號']
            suffix = ".TW" if row['市場別'] == '上市' else ".TWO"
            p_curr = get_realtime_price(code)
            if not p_curr: continue
            
            df_hist = get_historical_data(f"{code}{suffix}")
            if df_hist.empty or len(df_hist) < 2: continue
            
            # 漲幅與成交值計算
            if isinstance(df_hist.columns, pd.MultiIndex): df_hist.columns = df_hist.columns.get_level_values(0)
            df_hist = df_hist.dropna(subset=['Close'])
            p_yest = float(df_hist['Close'].iloc[-2]) if df_hist.index[-1].date() >= datetime.now().date() else float(df_hist['Close'].iloc[-1])
            chg = (p_curr - p_yest) / p_yest
            vol_amt = (df_hist['Volume'].iloc[-1] * p_curr) / 100000000 if df_hist.index[-1].date() >= datetime.now().date() else 0
            
            # 補完產業資訊
            info = stock_info_map.get(code, {})
            results.append({
                "市場別": row['市場別'],
                "代號": code,
                "名稱": row['名稱'],
                "近三月平均年增%": f"{row['YoY']:.2f}%",
                "現價": p_curr,
                "漲幅%": f"{chg*100:.1f}%",
                "成交值(億)": round(vol_amt, 1),
                "產業排位": info.get("產業排位", "-"),
                "族群細分": info.get("族群細分", "-")
            })
        return pd.DataFrame(results)

# ============================================================================
# 【主 UI 流程】
# ============================================================================

st.markdown("### 🏹 姊布林 ABCDE 策略戰情室 (即時優化版)")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

st.write(f"📅 **數據更新時間：{datetime.now(pytz.timezone('Asia/Taipei')).strftime('%Y/%m/%d %H:%M:%S')}**")

st.sidebar.title("🛠️ 設定區")
strategy_mode = st.sidebar.radio("📊 策略模式選擇", ["🏹 姊布林 ABCDE 策略", "💰 營收動能策略"])

if strategy_mode == "🏹 姊布林 ABCDE 策略":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        
        with st.spinner("分析個股環境中..."):
            for code in codes:
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                # 判定市場與獲取歷史資料
                m_type = "上市"; suffix = ".TW"; df = get_historical_data(f"{code}{suffix}")
                if df.empty or len(df) < 10: m_type = "上櫃"; suffix = ".TWO"; df = get_historical_data(f"{code}{suffix}")
                
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    current_env = m_env[m_type]
                    
                    # 均線與帶寬計算
                    today = datetime.now().date()
                    h_list = df['Close'].iloc[-20:-1].tolist() if df.index[-1].date() >= today else df['Close'].iloc[-19:].tolist()
                    close_20 = h_list + [p_curr]
                    m20_now = sum(close_20) / 20
                    std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2)
                    bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    
                    # 漲幅與量能
                    p_yest = h_list[-1]
                    chg = (p_curr - p_yest) / p_yest
                    vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000
                    ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
                    
                    # 邏輯過濾
                    res_tag = ""
                    fail = []
                    if p_curr <= upper_now: fail.append("未站上軌")
                    if m20_now <= sum(h_list)/20: fail.append("斜率負")
                    if vol_amt < 5: fail.append("量不足")
                    
                    if not fail:
                        if "🔴 紅燈" in main_market_light:
                            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        else:
                            if "🟢 綠燈" in current_env['燈號']:
                                env_de = (m_env['上市']['帶寬'] > 0.145 or m_env['上櫃']['帶寬'] > 0.095)
                                if env_de and bw > 0.2 and 0.8 <= ratio <= 1.2 and 0.03 <= chg <= 0.05: res_tag = "💎【D：共振】"
                                elif env_de and bw > 0.2 and 1.2 < ratio <= 2.0 and 0.03 <= chg <= 0.07: res_tag = "🚀【E：超額】"
                                elif 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                                elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                                elif 0.2 < bw <= 0.4 and 0.03 <= chg <= 0.07: res_tag = "🌊【C：瘋狗】"
                            elif "🟡 黃燈" in current_env['燈號']:
                                if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                                elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                    
                    info = stock_info_map.get(code, {"簡稱": f"台股{code}"})
                    results.append({
                        "代號": code, "名稱": info.get("簡稱"), "策略": res_tag or ("⚪ " + "/".join(fail)),
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                        "產業排位": info.get("產業排位", "-"), "族群細分": info.get("族群細分", "-")
                    })
            st.session_state.scan_results = pd.DataFrame(results)
    
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif strategy_mode == "💰 營收動能策略":
    st.markdown("#### 💰 營收動能策略結果")
    if st.sidebar.button("🚀 開始掃描營收動能"):
        st.session_state.revenue_results = build_revenue_momentum_results()
    
    if st.session_state.revenue_results is not None:
        if not st.session_state.revenue_results.empty:
            st.dataframe(st.session_state.revenue_results, use_container_width=True, hide_index=True)
        else: st.warning("⚠️ 未發現符合條件的營收動能個股 (均YoY > 20%)")
    else: st.info("💡 點擊左側按鈕開始掃描")

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
