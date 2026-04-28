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
def get_realtime_price_full(stock_id):
    """回傳現價、昨收、成交量(股)"""
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        text = response.text
        # 抓現價
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', text)
        # 抓昨收
        y_match = re.search(r'"regularMarketPreviousClose":\s*([0-9.]+)', text)
        # 抓成交量
        v_match = re.search(r'"regularMarketVolume":\s*([0-9.]+)', text)
        
        price = float(p_match.group(1)) if p_match else None
        yest = float(y_match.group(1)) if y_match else None
        vol = float(v_match.group(1)) if v_match else 0
        
        return price, yest, vol
    except:
        return None, None, 0

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

def get_local_revenue_safe(year_month):
    folder = "revenue_data"
    dfs = []
    for prefix in ["TWSE", "TPEX"]:
        file_path = os.path.join(os.getcwd(), folder, f"{prefix}_{year_month}.csv")
        if os.path.exists(file_path):
            try:
                try: df_l = pd.read_csv(file_path, encoding='utf-8-sig')
                except: df_l = pd.read_csv(file_path, encoding='cp950')
                df_l.columns = [str(c).strip() for c in df_l.columns]
                col = [c for c in df_l.columns if '去年同月增減' in c]
                if col:
                    dfs.append(df_l[['公司代號', '公司名稱', col[0]]].rename(columns={col[0]: '年增%'}))
            except: pass
    return pd.concat(dfs).drop_duplicates(subset=['公司代號']) if dfs else pd.DataFrame()

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "rev_results" not in st.session_state: st.session_state.rev_results = None

def set_ui_cleanup(image_file):
    b64_encoded = ""
    if os.path.exists(image_file):
        with open(image_file, "rb") as f: b64_encoded = base64.b64encode(f.read()).decode()
    st.markdown(f"""
    <style>
    .stApp {{ background-image: url("data:image/jpeg;base64,{b64_encoded}"); background-attachment: fixed; background-size: cover; background-position: center; }}
    .stApp::before {{ content: ""; position: absolute; top: 0; left: 0; width: 100%; height: 100%; background-color: rgba(0, 0, 0, 0.7); z-index: -1; }}
    /* 確保表格有滾動條 */
    .stDataFrame {{ overflow-x: auto !important; }}
    </style>
    """, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state: st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403": st.session_state.password_correct = True; st.rerun()
        else: st.error("密碼錯誤")
    st.stop()

# --- 3. 🛡️ 族群資料 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                try: df_local = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df_local = pd.read_csv(f_name, encoding='cp950')
                for _, row in df_local.fillna('-').iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {"簡稱": str(row.iloc[1]).strip(), "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-", "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-", "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-", "關鍵技術": str(row.iloc[5]).strip() if len(row) > 5 else "-"}
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 大盤環境 ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    idx_map = {"上市": ("TSE", "^TWII"), "上櫃": ("OTC", "^TWOII")}
    for k, (rt_id, yf_id) in idx_map.items():
        try:
            curr_p, _, _ = get_realtime_price_full(rt_id)
            df_h = get_historical_data(yf_id)
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                c_list = df_h['Close'].iloc[-19:].tolist() + [curr_p]
                m5, m20 = sum(c_list[-5:])/5, sum(c_list)/20
                bw = (pd.Series(c_list).std() * 4) / m20 if m20 != 0 else 0.0
                light = "🟢 綠燈" if curr_p > m5 else ("🟡 黃燈" if curr_p > m20 else "🔴 紅燈")
                res[k] = {"燈號": light, "價格": curr_p, "帶寬": bw}
            else: res[k] = {"燈號": "⚠️ 斷訊", "價格": 0.0, "帶寬": 0.0}
        except: res[k] = {"燈號": "⚠️ 錯誤", "價格": 0.0, "帶寬": 0.0}
    return res
m_env = get_market_env()

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
c1, c2 = st.columns(2)
c1.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
c2.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 6. 側邊欄 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇模式", ["🏹 姊布林個股掃描", "📈 營收動能 (三月平均 > 20%)"])

if mode == "🏹 姊布林個股掃描":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("掃描中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
                p_curr, p_yest, vol = get_realtime_price_full(code)
                if not p_curr: continue
                df = get_historical_data(f"{code}.TW")
                if df.empty or len(df) < 10: df = get_historical_data(f"{code}.TWO")
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    hist = df['Close'].iloc[-19:].tolist()
                    m20 = (sum(hist) + p_curr)/20
                    std = pd.Series(hist + [p_curr]).std()
                    bw = (std*4)/m20 if m20 != 0 else 0.0
                    chg = (p_curr - p_yest)/p_yest if p_yest else 0
                    vol_amt = (vol * p_curr) / 100000000
                    
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": "⚪ 觀察", 
                        "現價": p_curr, "漲跌幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 2),
                        "帶寬%": f"{bw*100:.1f}%", "產業排位": info["產業排位"], "族群": info["族群細分"]
                    })
        st.session_state.scan_results = pd.DataFrame(results)
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

elif mode == "📈 營收動能 (三月平均 > 20%)":
    if st.sidebar.button("🔍 執行營收全自動篩選"):
        yms = ["202603", "202602", "202601"]
        with st.spinner("正在計算近三月平均營收..."):
            r_list = [get_local_revenue_safe(ym) for ym in yms]
            if len([d for d in r_list if not d.empty]) >= 1:
                # 以最新的月份為基準進行合併
                merged = r_list[0].rename(columns={'年增%': 'm1'})
                for i, df_m in enumerate(r_list[1:], 2):
                    if not df_m.empty:
                        merged = pd.merge(merged, df_m[['公司代號', '年增%']].rename(columns={'年增%': f'm{i}'}), on='公司代號', how='inner')
                
                # 計算平均 (支援 1~3 個月的平均，以防檔案暫時缺漏)
                m_cols = [c for c in merged.columns if c.startswith('m')]
                merged['平均年增%'] = merged[m_cols].mean(axis=1)
                
                # 篩選 > 20%
                winners = merged[merged['平均年增%'] > 20.0].sort_values('平均年增%', ascending=False).head(50)
                
                final = []
                for _, r in winners.iterrows():
                    cid = str(r['公司代號']).strip()
                    p_curr, p_yest, vol = get_realtime_price_full(cid)
                    if p_curr:
                        chg = (p_curr - p_yest)/p_yest if p_yest else 0
                        vol_amt = (vol * p_curr) / 100000000
                        final.append({
                            "代號": cid, 
                            "名稱": r['公司名稱'], 
                            "三月平均年增%": f"{r['平均年增%']:.1f}%", 
                            "現價": p_curr, 
                            "漲跌幅%": f"{chg*100:.1f}%",
                            "成交值(億)": round(vol_amt, 2)
                        })
                st.session_state.rev_results = pd.DataFrame(final)
            else:
                st.error("❌ 檔案不足！請確保 revenue_data 資料夾內有 CSV 檔案。")
    
    if st.session_state.rev_results is not None:
        # 使用 st.dataframe 配合 use_container_width=True，當欄位多時會自動出現滾動條
        st.dataframe(st.session_state.rev_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
