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

# --- 0.1 🏎️ 歷史數據快取 ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    try:
        df = yf.download(code_with_suffix, period="2mo", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except:
        return pd.DataFrame()

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

# --- 3. 🛡️ 族群 CSV 讀取 (供兩個策略對齊產業資訊) ---
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
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-",
                            "實力指標": str(row.iloc[3]).strip() if len(row) > 3 else "-",
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

# --- 5. 側邊欄模式切換 ---
st.sidebar.markdown("---")
strategy_mode = st.sidebar.radio("📡 模式切換", ["姊布林策略", "營收動能策略"])

# ===================================================================================================
# --- 【區塊一：姊布林策略區塊】 ---
# ===================================================================================================
if strategy_mode == "姊布林策略":
    st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
    m_col1, m_col2 = st.columns(2)
    with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
    with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

    tw_tz = pytz.timezone('Asia/Taipei')
    st.write(f"📅 **更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

    st.sidebar.title("🛠️ 姊布林設定")
    raw_input = st.sidebar.text_area("輸入代碼", height=150)

    if st.sidebar.button("🚀 執行姊布林掃描") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        with st.spinner("掃描中..."):
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
                    df = df.dropna(subset=['Close'])
                    current_env = m_env[m_type]
                    if df.index[-1].date() >= datetime.now().date():
                        p_yest = float(df['Close'].iloc[-2])
                        h_list = df['Close'].iloc[-20:-1].tolist()
                    else:
                        p_yest = float(df['Close'].iloc[-1])
                        h_list = df['Close'].iloc[-19:].tolist()
                    c_20 = h_list + [p_curr]
                    m20 = sum(c_20)/20; std = pd.Series(c_20).std()
                    up = m20 + (std*2); bw = (std*4)/m20 if m20 != 0 else 0
                    chg = (p_curr-p_yest)/p_yest
                    vol = (df['Volume'].iloc[-1]*p_curr)/100000000
                    ratio = bw/current_env['帶寬'] if current_env['帶寬'] > 0 else 0
                    
                    res_tag = "⚪ 條件不符"
                    if p_curr > up and m20 > sum(h_list)/20 and vol >= 5:
                        if "🔴 紅燈" in main_market_light:
                            if 0.05<=bw<=0.1 and 0.03<=chg<=0.07: res_tag="🔥【A：潛龍】"
                            elif 0.1<bw<=0.2 and 0.03<=chg<=0.05: res_tag="🎯【B：海龍】"
                        else:
                            if "🟢 綠燈" in current_env['燈號']:
                                env_de = (m_env['上市']['帶寬']>0.145 or m_env['上櫃']['帶寬']>0.095)
                                if env_de and bw>0.2 and 0.8<=ratio<=1.2 and 0.03<=chg<=0.05: res_tag="💎【D：共振】"
                                elif env_de and bw>0.2 and 1.2<ratio<=2.0 and 0.03<=chg<=0.07: res_tag="🚀【E：超額】"
                                elif 0.05<=bw<=0.1 and 0.03<=chg<=0.07: res_tag="🔥【A：潛龍】"
                                elif 0.1<bw<=0.2 and 0.03<=chg<=0.05: res_tag="🎯【B：海龍】"
                                elif 0.2<bw<=0.4 and 0.03<=chg<=0.07: res_tag="🌊【C：瘋狗】"
                    results.append({
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol, 1),
                        "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                    })
            st.session_state.scan_results = pd.DataFrame(results)
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# ===================================================================================================
# --- 【區塊二：營收動能策略區塊】 ---
# ===================================================================================================
elif strategy_mode == "營收動能策略":
    st.markdown("### 📊 月營收動能掃描戰情室")
    
    def run_revenue_momentum():
        folder = "revenue_data"
        if not os.path.exists(folder):
            st.error("找不到 revenue_data 資料夾")
            return
        
        all_files = os.listdir(folder)
        
        def process_market(prefix):
            # 取得該市場最新 3 個月 CSV
            m_files = sorted([f for f in all_files if f.startswith(prefix)], reverse=True)[:3]
            if not m_files: return pd.DataFrame()
            
            combined_dfs = []
            for f in m_files:
                try:
                    # 7-1. 強制提取 4 欄位並清洗
                    df_r = pd.read_csv(os.path.join(folder, f), encoding='utf-8-sig')
                    df_r.columns = [c.strip() for c in df_r.columns]
                    target_cols = ['資料年月', '公司代號', '公司名稱', '營業收入-去年同月增減(%)']
                    df_r = df_r[target_cols].copy()
                    df_r['公司代號'] = df_r['公司代號'].astype(str).str.strip()
                    combined_dfs.append(df_r)
                except: continue
            
            if not combined_dfs: return pd.DataFrame()
            
            # 2-1. 合併並計算三個月平均 (加總/3)
            df_all = pd.concat(combined_dfs)
            df_avg = df_all.groupby(['公司代號', '公司名稱'])['營業收入-去年同月增減(%)'].mean().reset_index()
            df_avg.columns = ['代號', '名稱', '平均年增%']
            return df_avg[df_avg['平均年增%'] > 20]

        with st.spinner("計算營收動能中..."):
            df_twse = process_market("TWSE")
            df_tpex = process_market("TPEX")
            df_twse['市場別'] = '上市'
            df_tpex['市場別'] = '上櫃'
            
            final_list = pd.concat([df_twse, df_tpex], ignore_index=True)
            
            rev_results = []
            for _, row in final_list.iterrows():
                code = row['代號']
                # 7-2. 即時價格 (重複寫入以保證獨立性)
                p_now = get_realtime_price(code)
                if not p_now: continue
                
                # 抓取漲幅與成交值
                df_h = get_historical_data(f"{code}.TW" if row['市場別'] == '上市' else f"{code}.TWO")
                chg_str = "0.0%"; vol_bn = 0.0
                if not df_h.empty:
                    p_y = float(df_h['Close'].iloc[-1])
                    chg_str = f"{((p_now - p_y)/p_y)*100:.2f}%"
                    vol_bn = (df_h['Volume'].iloc[-1] * p_now) / 100000000

                # 7-3. 對齊產業與族群
                extra_info = stock_info_map.get(code, {"產業排位": "-", "族群細分": "-"})
                
                rev_results.append({
                    "市場別": row['市場別'],
                    "代號": code,
                    "名稱": row['名稱'],
                    "近三月平均年增%": round(row['平均年增%'], 2),
                    "現價": p_now,
                    "漲幅%": chg_str,
                    "成交值(億)": round(vol_bn, 2),
                    "產業排位": extra_info["產業排位"],
                    "族群細分": extra_info["族群細分"]
                })
            
            if rev_results:
                # 4. 顯示表格 (Streamlit 預設標題可點擊排序)
                st.dataframe(pd.DataFrame(rev_results), use_container_width=True, hide_index=True)
            else:
                st.warning("查無符合營收動能個股")

    if st.button("🔍 執行營收動能掃描"):
        run_revenue_momentum()

# --- 安全登出 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
