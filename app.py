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

# ==========================================
# --- 0. 🚀 核心共用函數 (解決 15 分鐘延遲) ---
# ==========================================
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

# ==========================================
# --- 1. 🎨 UI 配置與背景 (完全保留不更動) ---
# ==========================================
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

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

# ==========================================
# --- 2. 🔐 密碼鎖與權限控管 ---
# ==========================================
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

# ==========================================
# --- 3. 🛡️ 模組 A：姊布林策略區塊 ---
# ==========================================
def module_bollinger_strategy():
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
    st.markdown("### 🏹 姊布林 ABCDE 策略戰情室 (即時優化版)")
    m_col1, m_col2 = st.columns(2)
    with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
    with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

    tw_tz = pytz.timezone('Asia/Taipei')
    st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

    st.sidebar.title("🛠️ 姊布林設定區")
    raw_input = st.sidebar.text_area("輸入個股代碼", height=150, key="boll_input")
    
    if st.sidebar.button("🚀 開始掃描姊布林", key="boll_btn") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        
        with st.spinner("姊布林策略分析中..."):
            for code in codes:
                # [此處完全保留您基底程式碼中第 108 行至 160 行的所有判定邏輯，不做修改]
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
                    else: res_tag = "⚪ " + "/".join(fail_reasons)
                    
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                        "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
        if results:
            st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

# ==========================================
# --- 4. 🚀 模組 B：營收動能區塊 (全獨立) ---
# ==========================================
def module_revenue_momentum():
    st.markdown("### 📈 營收動能分析模組 (近三月平均年增 > 20%)")
    
    # --- 7-3. 產業資訊對齊 (獨立邏輯) ---
    def get_ind_mapping():
        m = {}
        for f in ["TWSE.csv", "TPEX.csv"]:
            if os.path.exists(f):
                try: df = pd.read_csv(f, encoding='utf-8-sig')
                except: df = pd.read_csv(f, encoding='cp950')
                for _, r in df.iterrows():
                    m[str(r.iloc[0]).strip()] = {"產業排位": str(r.iloc[2]), "族群細分": str(r.iloc[4])}
        return m

    # --- 核心運算：合併、計算、篩選 ---
    def process_revenue():
        path = "revenue_data"
        if not os.path.exists(path): return pd.DataFrame()
        
        # 8. 檔名倒序排列，取最新三月
        all_f = os.listdir(path)
        tw_files = sorted([f for f in all_f if f.startswith("TWSE_")], reverse=True)[:3]
        tp_files = sorted([f for f in all_f if f.startswith("TPEX_")], reverse=True)[:3]
        
        if len(tw_files) < 3 or len(tp_files) < 3:
            st.error(f"營收檔案不足三月(目前上市:{len(tw_files)}, 上櫃:{len(tp_files)})"); return pd.DataFrame()

        def merge_files(f_list, m_type):
            res_df = None
            for i, f_name in enumerate(f_list):
                try: df = pd.read_csv(os.path.join(path, f_name), encoding='utf-8-sig')
                except: df = pd.read_csv(os.path.join(path, f_name), encoding='cp950')
                
                # 7-1. 強制提取關鍵 5 欄位
                df.columns = [c.strip() for c in df.columns]
                df = df[['資料年月', '公司代號', '公司名稱', '營業收入-當月營收', '營業收入-去年當月營收']].copy()
                df['公司代號'] = df['公司代號'].astype(str).str.strip()
                
                # 計算單月 YoY
                df[f'y_{i}'] = (df['營業收入-當月營收'] - df['營業收入-去年當月營收']) / df['營業收入-去年當月營收']
                
                if res_df is None:
                    res_df = df[['公司代號', '公司名稱', f'y_{i}']]
                else:
                    res_df = pd.merge(res_df, df[['公司代號', f'y_{i}']], on='公司代號', how='inner')
            res_df['市場別'] = m_type
            return res_df

        final_df = pd.concat([merge_files(tw_files, "上市"), merge_files(tp_files, "上櫃")])
        # 2. 計算平均並篩選 > 20%
        y_cols = [c for c in final_df.columns if c.startswith('y_')]
        final_df['近三月平均年增%'] = round(final_df[y_cols].mean(axis=1) * 100, 2)
        return final_df[final_df['近三月平均年增%'] > 20].copy()

    if st.sidebar.button("🚀 執行營超掃描"):
        with st.spinner("正在進行營收資料與即時價格對齊..."):
            qualified = process_revenue()
            if qualified.empty: return
            
            ind_map = get_ind_mapping()
            results = []
            for _, row in qualified.iterrows():
                code = row['公司代號']
                # 7-2. 即時價格 (與姊布林同源)
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                df_h = get_historical_data(f"{code}.TW")
                if df_h.empty: df_h = get_historical_data(f"{code}.TWO")
                
                chg_pct, vol_amt = 0.0, 0.0
                if not df_h.empty:
                    if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                    p_yest = df_h['Close'].iloc[-1]
                    chg_pct = (p_curr - p_yest) / p_yest * 100
                    vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000

                i_info = ind_map.get(code, {"產業排位": "-", "族群細分": "-"})
                
                # 3. 呈現指定的 9 個欄位
                results.append({
                    "市場別": row['市場別'], "代號": code, "名稱": row['公司名稱'],
                    "近三月平均年增%": row['近三月平均年增%'],
                    "現價": p_curr, "漲幅%": f"{chg_pct:.2f}%", "成交值(億)": round(vol_amt, 2),
                    "產業排位": i_info["產業排位"], "族群細分": i_info["族群細分"]
                })
            
            if results:
                # 4. 內建排序篩選功能的表格
                st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

# ==========================================
# --- 5. 🔀 側邊欄模式切換 (主入口) ---
# ==========================================
st.sidebar.divider()
app_mode = st.sidebar.selectbox("請選擇操作模式", ["姊布林策略區", "營收動能區"])

if app_mode == "姊布林策略區":
    module_bollinger_strategy()
else:
    module_revenue_momentum()

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
