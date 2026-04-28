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

# --- 0. 🚀 即時數據抓取函數 (解決 15 分鐘延遲) ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id

    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 增加抓取昨收價以便計算漲跌幅
        p_patterns = [r'"regularMarketPrice":\s*([0-9.]+)', r'"price":\s*"([0-9,.]+)"']
        y_patterns = [r'"regularMarketPreviousClose":\s*([0-9.]+)', r'"previousClose":\s*"([0-9,.]+)"']
        v_patterns = [r'"regularMarketVolume":\s*([0-9.]+)', r'"volume":\s*"([0-9,.]+)"']

        price, yest, vol = None, None, 0
        
        for p in p_patterns:
            m = re.search(p, response.text)
            if m: price = float(m.group(1).replace(',', '')); break
        for p in y_patterns:
            m = re.search(p, response.text)
            if m: yest = float(m.group(1).replace(',', '')); break
        for p in v_patterns:
            m = re.search(p, response.text)
            if m: vol = float(m.group(1).replace(',', '')); break
            
        return price, yest, vol
    except:
        pass
    return None, None, 0

# --- 0.1 🏎️ 歷史數據快取 (提升搜尋速度) ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 0.2 📊 營收檔案讀取函數 ---
def get_revenue_data(ym):
    folder = "revenue_data"
    dfs = []
    # 依照要求：上市為 TWSE_YYYYMM, 上櫃為 TPEX_YYYYMM
    for prefix in ["TWSE", "TPEX"]:
        file_path = os.path.join(folder, f"{prefix}_{ym}.csv")
        if os.path.exists(file_path):
            try:
                try: df = pd.read_csv(file_path, encoding='utf-8-sig')
                except: df = pd.read_csv(file_path, encoding='cp950')
                df.columns = [str(c).strip() for c in df.columns]
                # 抓取年增率欄位 (通常包含「去年同月增減」字眼)
                target_col = [c for c in df.columns if '去年同月增減' in c]
                if target_col:
                    dfs.append(df[['公司代號', '公司名稱', target_col[0]]].rename(columns={target_col[0]: '年增%'}))
            except: pass
    return pd.concat(dfs).drop_duplicates(subset=['公司代號']) if dfs else pd.DataFrame()

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "rev_results" not in st.session_state: st.session_state.rev_results = None

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
st.markdown("### 🏹 姊布林 ABCDE & 營收動能戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 6. 側邊欄與模式切換 ---
st.sidebar.title("🛠️ 戰情總控室")
mode = st.sidebar.radio("切換掃描模式", ["姊布林 ABCDE 掃描", "📈 營收動能篩選"])

if mode == "姊布林 ABCDE 掃描":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        with st.spinner("姊布林策略分析中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
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
                    today_date = datetime.now().date()
                    if df.index[-1].date() >= today_date:
                        p_yest_val = float(df['Close'].iloc[-2])
                        history_for_ma = df['Close'].iloc[-20:-1].tolist()
                    else:
                        p_yest_val = float(df['Close'].iloc[-1])
                        history_for_ma = df['Close'].iloc[-19:].tolist()
                    
                    close_20 = history_for_ma + [p_curr]
                    m20_now = sum(close_20) / 20
                    std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2)
                    bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    chg = (p_curr - p_yest_val) / p_yest_val
                    vol_amt = (vol_raw * p_curr) / 100000000 
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
                    else:
                        res_tag = "⚪ " + "/".join(fail_reasons)

                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                        "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
            st.session_state.scan_results = pd.DataFrame(results)

    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif mode == "📈 營收動能篩選":
    if st.sidebar.button("🔍 執行營收全自動篩選"):
        # 依照要求：抓取近三月 (假設最新為 202603)
        yms = ["202603", "202602", "202601"]
        with st.spinner("讀取 CSV 並計算營收動能中..."):
            rev_dfs = [get_revenue_data(ym) for ym in yms]
            # 確保三個檔案都有讀到才進行
            valid_dfs = [d for d in rev_dfs if not d.empty]
            if len(valid_dfs) == 3:
                merged = valid_dfs[0].rename(columns={'年增%': 'm1'})
                merged = pd.merge(merged, valid_dfs[1][['公司代號', '年增%']].rename(columns={'年增%': 'm2'}), on='公司代號')
                merged = pd.merge(merged, valid_dfs[2][['公司代號', '年增%']].rename(columns={'年增%': 'm3'}), on='公司代號')
                
                merged['三月平均年增%'] = merged[['m1', 'm2', 'm3']].mean(axis=1)
                # 條件 2: 近三月平均年增率 > 20%
                winners = merged[merged['三月平均年增%'] > 20.0]
                
                final_results = []
                for _, row in winners.iterrows():
                    cid = str(row['公司代號']).strip()
                    info = stock_info_map.get(cid, {"簡稱": row['公司名稱'], "產業排位": "-", "族群細分": "-"})
                    p_curr, p_yest, vol_raw = get_realtime_price(cid)
                    if p_curr:
                        chg = (p_curr - p_yest) / p_yest if p_yest else 0
                        vol_amt = (vol_raw * p_curr) / 100000000
                        final_results.append({
                            "代號": cid, "名稱": info["簡稱"], 
                            "近三月平均年增%": round(row['三月平均年增%'], 2),
                            "現價": p_curr, "漲幅%": f"{chg*100:.1f}%",
                            "成交值(億)": round(vol_amt, 2),
                            "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                        })
                st.session_state.rev_results = pd.DataFrame(final_results)
            else:
                st.error("❌ 檔案不足！請檢查 revenue_data 資料夾內是否包含 202601~03 的上市上櫃 CSV 檔。")

    if st.session_state.rev_results is not None:
        # 條件 4: 標題支援篩選排序 (st.dataframe 預設即支援點擊標題排序)
        st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.rev_results = None
    st.rerun()
