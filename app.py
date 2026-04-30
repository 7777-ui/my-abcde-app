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

# --- 0. 🚀 即時數據抓取函數 ---
@st.cache_data(ttl=10)
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

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

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

# --- 3. 🛡️ 族群 CSV 讀取 ---
@st.cache_data(ttl=604800)
def get_stock_info_full():
    mapping = {}
    file_configs = {"TWSE.csv": "上市", "TPEX.csv": "上櫃"}
    for f_name, market_label in file_configs.items():
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
                            "市場": market_label,
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
    rt_indices = {"上市": "TSE", "上櫃": "OTC"}
    yf_indices = {"上市": "^TWII", "上櫃": "^TWOII"}
    for k, v in rt_indices.items():
        try:
            curr_p = get_realtime_price(v)
            df_h = get_historical_data(yf_indices[k])
            if not df_h.empty and curr_p:
                if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                df_h = df_h.dropna(subset=['Close'])
                base_list = df_h['Close'].iloc[-20:-1].tolist()
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
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

# --- 8. 營收動能策略 (🛠️ 重大修正：分資料夾與倒序排列) ---
if mode == "營收動能策略":
    st.sidebar.info("💡 獨立分析 TWSE 與 TPEX 資料夾最新 3 個月營收。")
    if st.sidebar.button("📊 啟動營收動能分析"):
        
        final_list = []
        # 定義市場資料夾配置
        market_configs = [
            ("revenue_data_TWSE", "上市", ".TW"),
            ("revenue_data_TPEX", "上櫃", ".TWO")
        ]

        for folder, m_label, suffix in market_configs:
            if not os.path.exists(folder):
                st.error(f"❌ 找不到資料夾: {folder}")
                continue
            
            # 檔名倒序排序，抓取最新 3 個 CSV
            all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
            
            if len(all_files) < 3:
                st.warning(f"⚠️ {m_label} 資料不足 3 份，跳過。")
                continue
            
            recent_files = all_files[:3]
            month_dfs = []

            for f in recent_files:
                try:
                    try: t_df = pd.read_csv(f, encoding='utf-8-sig')
                    except: t_df = pd.read_csv(f, encoding='cp950')
                    
                    t_df.columns = [c.strip() for c in t_df.columns]
                    
                    # 強制提取指定 4 個欄位 (或根據 CSV 實際名稱微調)
                    target_cols = {
                        '資料年月': 'Date',
                        '公司代號': 'ID',
                        '公司名稱': 'Name',
                        '營業收入-去年同月增減(%)': 'YoY'
                    }
                    # 檢查欄位是否存在，不存在則跳過
                    if all(c in t_df.columns for c in target_cols.keys()):
                        t_df = t_df[list(target_cols.keys())].rename(columns=target_cols)
                        t_df['ID'] = t_df['ID'].astype(str).str.strip()
                        t_df['YoY'] = pd.to_numeric(t_df['YoY'], errors='coerce')
                        month_dfs.append(t_df.drop_duplicates('ID'))
                except: continue

            if len(month_dfs) == 3:
                # 合併三個月資料計算平均
                m1, m2, m3 = month_dfs[0], month_dfs[1], month_dfs[2]
                merged = m1.merge(m2[['ID', 'YoY']], on='ID', suffixes=('', '2'))
                merged = merged.merge(m3[['ID', 'YoY']], on='ID', suffixes=('', '3'))
                merged['avg_growth'] = (merged['YoY'] + merged['YoY2'] + merged['YoY3']) / 3
                
                # 篩選平均年增 > 20%
                targets = merged[merged['avg_growth'] > 20].copy()
                
                for _, row in targets.iterrows():
                    code = row['ID']
                    p_curr = get_realtime_price(code)
                    if not p_curr: continue
                    
                    # 取得即時技術面數據
                    df_h = get_historical_data(f"{code}{suffix}")
                    if not df_h.empty:
                        if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                        p_yest = float(df_h['Close'].iloc[-1])
                        chg = (p_curr - p_yest) / p_yest
                        vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                        
                        info = stock_info_map.get(code, {})
                        final_list.append({
                            "市場": m_label,
                            "代號": code, "名稱": row['Name'], 
                            "三月均年增%": f"{row['avg_growth']:.1f}%",
                            "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", 
                            "成交值(億)": round(vol_amt, 1),
                            "產業排位": info.get("產業排位", "-"),
                            "族群細分": info.get("族群細分", "-")
                        })
        
        if final_list:
            st.session_state.scan_results = pd.DataFrame(final_list)
        else:
            st.info("查無符合營收動能之個股。")

# --- 9. 顯示結果 ---
if st.session_state.scan_results is not None:
    st.markdown("### 📊 掃描結果")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
