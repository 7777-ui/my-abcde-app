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

# ==========================================
# --- 0. 基礎配置與通用函數 (維持基底) ---
# ==========================================
st.set_page_config(page_title="🏹 策略戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

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

# --- 密碼鎖 (維持基底) ---
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

# --- 族群數據讀取 (維持基底) ---
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
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"
                        }
            except: pass
    return mapping

stock_info_map = get_stock_info_full()

@st.cache_data(ttl=60)
def get_market_env():
    res = {}
    for k, v in {"上市": "TSE", "上櫃": "OTC"}.items():
        try:
            curr_p = get_realtime_price(v)
            yf_id = "^TWII" if k == "上市" else "^TWOII"
            df_h = get_historical_data(yf_id)
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

# --- 主標題與大盤資訊 ---
st.markdown(f"### 🏹 策略戰情室 - 模式：{st.sidebar.get_option if 'mode' in st.session_state else ''}")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# ==========================================
# --- 1. 側邊欄配置 (切換開關) ---
# ==========================================
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

if "scan_results" not in st.session_state: st.session_state.scan_results = None

# ==========================================
# --- 2. 營收動能策略區塊 (全新獨立) ---
# ==========================================
def run_revenue_strategy():
    results = []
    folder = "revenue_data"
    if not os.path.exists(folder):
        st.error(f"找不到 {folder} 資料夾")
        return None
    
    # 掃描所有 CSV 並按檔名排序取最近 3 個
    all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
    if len(all_files) < 3:
        st.warning("營收資料夾內的 CSV 檔案不足 3 個月，將以現有檔案計算。")
    
    recent_files = all_files[:3]
    dfs = []
    for f in recent_files:
        try:
            temp_df = pd.read_csv(f, encoding='utf-8-sig')
        except:
            temp_df = pd.read_csv(f, encoding='cp950')
        
        # 僅保留核心欄位
        keep_cols = ['資料年月', '公司代號', '公司名稱', '營業收入-當月營收', '去年同月增減(%)']
        temp_df = temp_df[[c for c in keep_cols if c in temp_df.columns]]
        temp_df['公司代號'] = temp_df['公司代號'].astype(str).str.strip()
        dfs.append(temp_df)
    
    # 合併計算平均年增率
    if not dfs: return None
    
    # 以第一個月(最新月)為基準
    base_df = dfs[0].copy()
    
    # 合併計算平均值 (這裡假設 CSV 裡已有 '去年同月增減(%)')
    # 如果要手動算，需讀取去年資料。依您的需求 7-1，我們取這三份文件的年增率欄位做平均。
    combined = pd.concat(dfs)
    avg_growth = combined.groupby('公司代號')['去年同月增減(%)'].mean().reset_index()
    avg_growth.columns = ['公司代號', '三月平均年增%']
    
    # 篩選 > 20%
    target_stocks = avg_growth[avg_growth['三月平均年增%'] > 20]
    
    with st.spinner(f"正在分析 {len(target_stocks)} 檔高營收成長股..."):
        for _, row in target_stocks.iterrows():
            code = row['公司代號']
            avg_val = row['三月平均年增%']
            
            # 獲取基礎資料 (對齊姊布林來源)
            info = stock_info_map.get(code, {"簡稱": "未知", "產業排位": "-", "族群細分": "-"})
            p_curr = get_realtime_price(code)
            if not p_curr: continue
            
            # 獲取漲幅與成交值 (對齊姊布林來源)
            df_h = get_historical_data(f"{code}.TW")
            if df_h.empty: df_h = get_historical_data(f"{code}.TWO")
            
            if not df_h.empty:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                p_yest = float(df_h['Close'].iloc[-1])
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                
                results.append({
                    "代號": code,
                    "名稱": info["簡稱"],
                    "近三月平均年增%": f"{avg_val:.2f}%",
                    "現價": p_curr,
                    "漲幅%": f"{chg*100:.1f}%",
                    "成交值(億)": round(vol_amt, 1),
                    "產業排位": info["產業排位"],
                    "族群細分": info["族群細分"]
                })
    return pd.DataFrame(results)

# ==========================================
# --- 3. 姊布林策略區塊 (維持原始邏輯) ---
# ==========================================
def run_bollinger_strategy(raw_input):
    codes = re.findall(r'\b\d{4,6}\b', raw_input)
    results = []
    main_market_light = m_env['上市']['燈號']
    
    for code in codes:
        info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
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
            today_date = datetime.now().date()
            if df.index[-1].date() >= today_date:
                p_yest = float(df['Close'].iloc[-2]); history_for_ma = df['Close'].iloc[-20:-1].tolist()
            else:
                p_yest = float(df['Close'].iloc[-1]); history_for_ma = df['Close'].iloc[-19:].tolist()
            
            close_20 = history_for_ma + [p_curr]
            m20_now = sum(close_20) / 20
            std_now = pd.Series(close_20).std()
            upper_now = m20_now + (std_now * 2)
            bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
            chg = (p_curr - p_yest) / p_yest
            vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000 
            ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
            slope_pos = m20_now > sum(history_for_ma) / 20
            break_upper = p_curr > upper_now
            
            res_tag = ""
            fail_reasons = []
            if not break_upper: fail_reasons.append("未站上軌")
            if not slope_pos: fail_reasons.append("斜率負")
            if vol_amt < 5: fail_reasons.append("量不足")

            if not fail_reasons:
                if "🔴 紅燈" in main_market_light:
                    if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                    elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                    else: res_tag = "⚪ 參數不符(大盤紅燈限AB)"
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
                    elif "🔴 紅燈" in current_env['燈號']:
                        if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                if not res_tag: res_tag = "⚪ 參數不符"
            else: res_tag = "⚪ " + "/".join(fail_reasons)

            results.append({
                "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                "產業排位": info["產業排位"], "2026指標": info["實力指標"],
                "族群細分": info["族群細分"], "關鍵技術": info["關鍵技術"]
            })
    return pd.DataFrame(results)

# ==========================================
# --- 4. 執行與顯示介面 ---
# ==========================================
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼 (姊布林模式)", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林"):
        if raw_input:
            st.session_state.scan_results = run_bollinger_strategy(raw_input)
        else:
            st.warning("請先輸入代碼")

elif mode == "營收動能策略":
    st.sidebar.info("💡 系統將自動讀取 revenue_data 資料夾並計算近三月平均年增率 > 20% 之個股。")
    if st.sidebar.button("📊 啟動營收動能分析"):
        st.session_state.scan_results = run_revenue_strategy()

# --- 顯示結果表格 (支援排序篩選) ---
if st.session_state.scan_results is not None:
    st.write(f"### 📋 掃描結果 - {mode}")
    # Streamlit dataframe 預設就支援點擊標題排序
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# --- 登出按鈕 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
