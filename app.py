import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import io
import time
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh

# --- 0. 🚀 核心抓取函數 ---
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

@st.cache_data(ttl=86400)
def get_monthly_revenue_mops(year, month):
    """從公開資訊觀測站抓取每月營收彙整表"""
    url = f"https://mops.twse.com.tw/nas/t110/stock/t110sc17_{year}_{month}_0.html"
    try:
        response = requests.get(url, timeout=10)
        response.encoding = 'cp950'
        dfs = pd.read_html(io.StringIO(response.text))
        combined_df = pd.concat([df for df in dfs if "公司代號" in df.columns])
        combined_df.columns = [str(c[1]) if isinstance(c, tuple) else str(c) for c in combined_df.columns]
        return combined_df[['公司代號', '公司名稱', '去年同月增減(%)']]
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    try:
        time.sleep(0.1) # 稍微延遲避免被 yfinance 封鎖
        return yf.download(code_with_suffix, period="2mo", progress=False)
    except: return pd.DataFrame()

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林戰情室", page_icon="🏹", layout="wide")
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
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; }}
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

# --- 3. 🛡️ 族群資料載入 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    files = ["TWSE.csv", "TPEX.csv"] 
    for f_name in files:
        if os.path.exists(f_name):
            for enc in ['utf-8-sig', 'cp950', 'big5']:
                try:
                    df_local = pd.read_csv(f_name, encoding=enc).fillna('-')
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
                    break 
                except: continue
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

# --- 5. 側邊欄與模式切換 ---
st.sidebar.title("🛠️ 戰情總部")
mode = st.sidebar.radio("切換分析模式", ["🏹 姊布林 ABCDE", "📈 營收動能 (年增>20%)"])

# --- 模式 1: 姊布林 ABCDE ---
if mode == "🏹 姊布林 ABCDE":
    st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
    c1, c2 = st.columns(2)
    c1.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
    c2.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

    raw_input = st.sidebar.text_area("輸入股票代碼 (姊布林模式)", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("分析中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                df = get_historical_data(f"{code}.TW")
                m_type = "上市"
                if df.empty or len(df) < 10:
                    df = get_historical_data(f"{code}.TWO"); m_type = "上櫃"
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    curr_m_env = m_env[m_type]
                    p_yest = float(df['Close'].iloc[-2]) if df.index[-1].date() >= datetime.now().date() else float(df['Close'].iloc[-1])
                    history_for_ma = df['Close'].iloc[-20:-1].tolist() if df.index[-1].date() >= datetime.now().date() else df['Close'].iloc[-19:].tolist()
                    close_20 = history_for_ma + [p_curr]
                    m20_now = sum(close_20) / 20; std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2); bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    chg = (p_curr - p_yest) / p_yest; vol_amt = (df['Volume'].iloc[-1] * p_curr) / 100000000 
                    ratio = bw / curr_m_env['帶寬'] if curr_m_env['帶寬'] > 0 else 0
                    res_tag = "⚪ 參數不符"
                    # ... (此處保留您原有的 A/B/C/D/E 判定邏輯) ...
                    if p_curr > upper_now and m20_now > sum(history_for_ma)/20 and vol_amt >= 5:
                        if "🔴 紅燈" in m_env['上市']['燈號']:
                            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                        else:
                            if 0.05 <= bw <= 0.1: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2: res_tag = "🎯【B：海龍】"
                            elif 0.2 < bw <= 0.4: res_tag = "🌊【C：瘋狗】"

                    results.append({"代號": code, "名稱": info["簡稱"], "策略": res_tag, "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1), "個股帶寬%": f"{bw*100:.2f}%", "產業排位": info["產業排位"], "族群細分": info["族群細分"]})
        st.session_state.scan_results = pd.DataFrame(results)

# --- 模式 2: 營收動能 (自動全市場掃描) ---
elif mode == "📈 營收動能 (年增>20%)":
    st.markdown("### 📈 近三個月營收平均年增 > 20% 戰情室")
    if st.sidebar.button("🔍 執行全市場掃描"):
        results = []
        now = datetime.now()
        dates = []
        # 取得最近三個月的年月
        for i in range(1, 4):
            d = (now.replace(day=1) - timedelta(days=i*28)).replace(day=1)
            dates.append((d.year - 1911, d.month))
        
        with st.spinner("正在計算營收數據..."):
            rev_dfs = []
            for y, m in dates:
                df_m = get_monthly_revenue_mops(y, m)
                if not df_m.empty:
                    df_m['公司代號'] = df_m['公司代號'].astype(str).str.strip()
                    df_m['去年同月增減(%)'] = pd.to_numeric(df_m['去年同月增減(%)'], errors='coerce')
                    rev_dfs.append(df_m)
            
            if len(rev_dfs) >= 2:
                final_rev = rev_dfs[0].copy().rename(columns={'去年同月增減(%)': 'm1'})
                for i, df_next in enumerate(rev_dfs[1:]):
                    final_rev = pd.merge(final_rev, df_next[['公司代號', '去年同月增減(%)']], on='公司代號', how='inner')
                    final_rev = final_rev.rename(columns={'去年同月增減(%)': f'm{i+2}'})
                
                final_rev['平均年增%'] = final_rev[[f'm{j+1}' for j in range(len(rev_dfs))]].mean(axis=1)
                filtered = final_rev[final_rev['平均年增%'] > 20.0].sort_values('平均年增%', ascending=False)
                
                status = st.empty()
                for idx, row in filtered.head(60).iterrows(): # 先取成長最高的前 60 檔抓現價
                    code = row['公司代號']
                    status.text(f"正在更新報價: {code}")
                    p_curr = get_realtime_price(code)
                    if p_curr:
                        hist = get_historical_data(f"{code}.TW" if len(code)<=4 else f"{code}.TWO")
                        if not hist.empty:
                            if isinstance(hist.columns, pd.MultiIndex): hist.columns = hist.columns.get_level_values(0)
                            p_yest = hist['Close'].iloc[-2] if hist.index[-1].date() >= datetime.now().date() else hist['Close'].iloc[-1]
                            chg = (p_curr - p_yest) / p_yest
                            vol_amt = (hist['Volume'].iloc[-1] * p_curr) / 100000000
                            results.append({
                                "代號": code, "簡稱": row['公司名稱'], 
                                "三月平均年增%": f"{row['平均年增%']:.1f}%", 
                                "現價": p_curr, "漲跌幅%": f"{chg*100:+.1f}%",
                                "成交值(億)": round(vol_amt, 2)
                            })
                st.session_state.rev_results = pd.DataFrame(results)
                status.empty()

# --- 7. 顯示結果 ---
if mode == "🏹 姊布林 ABCDE" and "scan_results" in st.session_state:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if mode == "📈 營收動能 (年增>20%)" and "rev_results" in st.session_state:
    st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
