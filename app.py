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
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id

    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        patterns = [
            r'"regularMarketPrice":\s*([0-9.]+)',
            r'"price":\s*"([0-9,.]+)"'
        ]
        for p in patterns:
            match = re.search(p, response.text)
            if match:
                val = float(match.group(1).replace(',', ''))
                if val > 0: return val
    except:
        pass
    return None

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 戰情室總控", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "revenue_results" not in st.session_state:
    st.session_state.revenue_results = None

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

# --- 3. 🛡️ 基礎資料庫讀取 ---
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
                            "市場別": "上市" if "TWSE" in f_name else "上櫃"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_full()

# --- 4. 營收動能計算區塊 (獨立區塊) ---
@st.cache_data(ttl=86400)
def get_revenue_momentum():
    folder = "revenue_data"
    if not os.path.exists(folder): return pd.DataFrame()
    
    all_res = []
    for prefix in ["TWSE", "TPEX"]:
        files = sorted(glob.glob(os.path.join(folder, f"{prefix}_*.csv")), reverse=True)[:3]
        if len(files) < 3: continue
        
        dfs = []
        for f in files:
            try:
                # 強制提取指定欄位
                temp_df = pd.read_csv(f)
                temp_df = temp_df[['資料年月', '公司代號', '公司名稱', '營業收入-去年同月增減(%)']]
                temp_df['公司代號'] = temp_df['公司代號'].astype(str)
                dfs.append(temp_df)
            except: continue
        
        if dfs:
            # 合併三個月資料並計算平均
            merged = pd.concat(dfs)
            avg_rev = merged.groupby(['公司代號', '公司名稱'])['營業收入-去年同月增減(%)'].mean().reset_index()
            avg_rev.columns = ['代號', '名稱', '近三月平均年增%']
            avg_rev = avg_rev[avg_rev['近三月平均年增%'] > 20]
            avg_rev['市場別'] = "上市" if prefix == "TWSE" else "上櫃"
            all_res.append(avg_rev)
            
    return pd.concat(all_res) if all_res else pd.DataFrame()

# --- 5. 大盤環境偵測 ---
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

# --- 6. 主畫面顯示 ---
st.markdown(f"### 🏹 策略戰情總控中心")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 7. 側邊欄控制項 ---
mode = st.sidebar.radio("📡 切換模式", ["姊布林策略掃描", "營收動能策略"])

if mode == "姊布林策略掃描":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        with st.spinner("分析中..."):
            for code in codes:
                # --- 原始姊布林邏輯 (保持不動) ---
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "族群細分": "-"})
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                df = get_historical_data(f"{code}.TW")
                m_type = "上市"
                if df.empty or len(df) < 10:
                    df = get_historical_data(f"{code}.TWO"); m_type = "上櫃"
                
                if not df.empty and len(df) >= 20:
                    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                    df = df.dropna(subset=['Close'])
                    current_env = m_env[m_type]
                    today_date = datetime.now().date()
                    if df.index[-1].date() >= today_date:
                        p_yest = float(df['Close'].iloc[-2])
                        history_for_ma = df['Close'].iloc[-20:-1].tolist()
                        vol_val = df['Volume'].iloc[-1]
                    else:
                        p_yest = float(df['Close'].iloc[-1])
                        history_for_ma = df['Close'].iloc[-19:].tolist()
                        vol_val = df['Volume'].iloc[-1]

                    close_20 = history_for_ma + [p_curr]
                    m20_now = sum(close_20) / 20
                    std_now = pd.Series(close_20).std()
                    upper_now = m20_now + (std_now * 2)
                    bw = (std_now * 4) / m20_now if m20_now != 0 else 0.0
                    chg = (p_curr - p_yest) / p_yest
                    vol_amt = (vol_val * p_curr) / 100000000 
                    ratio = bw / current_env['帶寬'] if current_env['帶寬'] > 0 else 0
                    
                    res_tag = ""
                    # [判斷邏輯 A/B/C/D/E 略，保持原狀...]
                    if p_curr > upper_now and m20_now > (sum(history_for_ma)/20) and vol_amt >= 5:
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
                    
                    if not res_tag: res_tag = "⚪ 未達標"
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag, "現價": p_curr, 
                        "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
            st.session_state.scan_results = pd.DataFrame(results)

elif mode == "營收動能策略":
    if st.sidebar.button("📊 執行營收動能篩選"):
        with st.spinner("正在計算近三月平均營收..."):
            rev_df = get_revenue_momentum()
            final_rev = []
            for _, row in rev_df.iterrows():
                code = row['代號']
                p_curr = get_realtime_price(code)
                if not p_curr: continue
                
                # 取得即時漲幅與成交量 (比照姊布林來源)
                df_h = get_historical_data(f"{code}.TW" if row['市場別']=="上市" else f"{code}.TWO")
                if df_h.empty: continue
                p_yest = float(df_h['Close'].iloc[-2]) if len(df_h)>1 else p_curr
                chg = (p_curr - p_yest) / p_yest
                vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                
                # 對齊產業與族群
                info = stock_info_map.get(code, {"產業排位": "-", "族群細分": "-"})
                
                final_rev.append({
                    "市場別": row['市場別'], "代號": code, "名稱": row['名稱'],
                    "近三月平均年增%": round(row['近三月平均年增%'], 2),
                    "現價": p_curr, "漲幅%": f"{chg*100:.1f}%",
                    "成交值(億)": round(vol_amt, 1),
                    "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                })
            st.session_state.revenue_results = pd.DataFrame(final_rev)

# --- 8. 顯示結果區 ---
if mode == "姊布林策略掃描" and st.session_state.scan_results is not None:
    st.subheader("🎯 姊布林策略掃描結果")
    st.dataframe(st.session_state.scan_results.sort_values("策略"), use_container_width=True, hide_index=True)

if mode == "營收動能策略" and st.session_state.revenue_results is not None:
    st.subheader("📈 營收動能篩選 (近三月平均 > 20%)")
    # 這裡的 dataframe 會自動帶有 Streamlit 原生的篩選與排序功能
    st.dataframe(st.session_state.revenue_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.rerun()
