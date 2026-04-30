import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import pytz
import requests
import glob
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 🎨 視覺樣式與背景 (修復背景消失問題) ---
def set_bg_style():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-image: url("https://images.unsplash.com/photo-1590283603385-17ffb3a7f29f?q=80&w=2070&auto=format&fit=crop");
            background-attachment: fixed;
            background-size: cover;
        }}
        .stMarkdown, .stDataFrame, .stTable {{
            background-color: rgba(255, 255, 255, 0.9);
            border-radius: 10px;
            padding: 10px;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

# --- 1. 🚀 核心抓取函數 ---
@st.cache_data(ttl=10)
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        if match: return float(match.group(1))
    except: pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 2. 網頁配置與背景啟動 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
set_bg_style()
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# --- 3. 🔐 密碼鎖 (密碼: test0403) ---
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

# --- 4. 🛡️ 族群資料庫讀取 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    for f_name, market in [("TWSE.csv", "上市"), ("TPEX.csv", "上櫃")]:
        if os.path.exists(f_name):
            try:
                df = pd.read_csv(f_name, encoding='utf-8-sig')
                for _, row in df.iterrows():
                    code = str(row.iloc[0]).strip()
                    mapping[code] = {
                        "市場": market,
                        "產業排位": str(row.iloc[2]) if len(row)>2 else "-",
                        "族群細分": str(row.iloc[4]) if len(row)>4 else "-"
                    }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 5. 主畫面標題 ---
tw_tz = pytz.timezone('Asia/Taipei')
st.markdown(f"### 🏹 姊布林 ABCDE 策略戰情室")
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

# --- 6. 營收動能策略 (🛠️ /optimize: 強化欄位匹配) ---
if mode == "營收動能策略":
    if st.sidebar.button("📊 啟動營收動能分析"):
        final_targets = []
        folder_configs = [("revenue_data_TWSE", "上市"), ("revenue_data_TPEX", "上櫃")]
        
        progress_bar = st.progress(0)
        
        for idx, (folder, m_label) in enumerate(folder_configs):
            if not os.path.exists(folder):
                st.warning(f"找不到路徑: {folder}")
                continue
            
            # 檔案倒序排列，取最新三個月
            all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
            if len(all_files) < 3:
                st.warning(f"{m_label} 資料不足 3 個月")
                continue
            
            month_dfs = []
            for f in all_files[:3]:
                try:
                    df_t = pd.read_csv(f, encoding='utf-8-sig')
                    # 模糊匹配欄位，防止空格干擾
                    def find_col(keywords):
                        for c in df_t.columns:
                            if any(k in c for k in keywords): return c
                        return None
                    
                    c_id = find_col(['公司代號', '代號'])
                    c_name = find_col(['公司名稱', '名稱'])
                    c_now = find_col(['營業收入-當月營收', '當月營收'])
                    c_last = find_col(['營業收入-去年當月營收', '去年當月營收'])
                    
                    if all([c_id, c_now, c_last]):
                        df_t = df_t[[c_id, c_name, c_now, c_last]].copy()
                        df_t.columns = ['ID', 'Name', 'Now', 'Last']
                        df_t['ID'] = df_t['ID'].astype(str).str.strip()
                        df_t['Now'] = pd.to_numeric(df_t['Now'].astype(str).str.replace(',',''), errors='coerce')
                        df_t['Last'] = pd.to_numeric(df_t['Last'].astype(str).str.replace(',',''), errors='coerce')
                        df_t['yoy'] = (df_t['Now'] - df_t['Last']) / df_t['Last']
                        month_dfs.append(df_t[['ID', 'Name', 'yoy']])
                except: continue

            if len(month_dfs) == 3:
                # 確保 ID 唯一後合併
                m1, m2, m3 = [d.drop_duplicates('ID') for d in month_dfs]
                merged = m1.merge(m2[['ID', 'yoy']], on='ID', suffixes=('', '_2'))
                merged = merged.merge(m3[['ID', 'yoy']], on='ID', suffixes=('', '_3'))
                merged['avg_growth'] = merged[['yoy', 'yoy_2', 'yoy_3']].mean(axis=1) * 100
                
                # 篩選平均增長 > 20%
                targets = merged[merged['avg_growth'] > 20].copy()
                
                for _, row in targets.iterrows():
                    code = row['ID']
                    suffix = ".TW" if m_label == "上市" else ".TWO"
                    p_curr = get_realtime_price(code)
                    if not p_curr: continue
                    
                    df_h = get_historical_data(f"{code}{suffix}")
                    if not df_h.empty:
                        if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                        p_yest = float(df_h['Close'].iloc[-1])
                        vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                        info = stock_info_map.get(code, {})
                        
                        final_targets.append({
                            "市場": m_label, "代號": code, "名稱": row['Name'],
                            "均年增%": f"{row['avg_growth']:.1f}%",
                            "現價": p_curr, "漲幅%": f"{((p_curr-p_yest)/p_yest)*100:.1f}%",
                            "成交億": round(vol_amt, 1),
                            "族群": info.get("族群細分", "-"),
                            "排位": info.get("產業排位", "-")
                        })
            progress_bar.progress((idx + 1) / len(folder_configs))
            
        if final_targets:
            st.session_state.scan_results = pd.DataFrame(final_targets)
        else:
            st.error("❌ 掃描完成，但沒有符合條件的股票。請確認 CSV 檔案夾內是否有對應月份資料。")

# --- 7. 呈現結果 ---
if st.session_state.scan_results is not None:
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
