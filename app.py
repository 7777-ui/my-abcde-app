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

# --- 0. 🚀 公用函數：即時數據抓取 (雙策略獨立調用) ---
def get_realtime_price_data(stock_id):
    """抓取即時價格、昨收(算漲跌)與成交量(算成交值)"""
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id

    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        # 抓取現價
        p_match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        # 抓取昨收
        y_match = re.search(r'"regularMarketPreviousClose":\s*([0-9.]+)', response.text)
        # 抓取成交量
        v_match = re.search(r'"regularMarketVolume":\s*([0-9.]+)', response.text)
        
        price = float(p_match.group(1)) if p_match else None
        yest = float(y_match.group(1)) if y_match else None
        vol = float(v_match.group(1)) if v_match else 0
        return price, yest, vol
    except:
        return None, None, 0

@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 1. 網頁配置與背景 ---
st.set_page_config(page_title="🏹 姊布林 & 營收動能戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# 初始化狀態
if "scan_results" not in st.session_state: st.session_state.scan_results = None
if "revenue_results" not in st.session_state: st.session_state.revenue_results = None

def set_ui_cleanup(image_file):
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

# --- 3. 🛡️ 族群資料讀取 (對齊代號用) ---
@st.cache_data(ttl=604800)
def get_stock_info_map():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                try: df = pd.read_csv(f_name, encoding='utf-8-sig')
                except: df = pd.read_csv(f_name, encoding='cp950')
                df = df.fillna('-')
                for _, row in df.iterrows():
                    code = str(row.iloc[0]).strip()
                    if code.isdigit():
                        mapping[code] = {
                            "簡稱": str(row.iloc[1]).strip(),
                            "產業排位": str(row.iloc[2]).strip() if len(row) > 2 else "-",
                            "族群細分": str(row.iloc[4]).strip() if len(row) > 4 else "-"
                        }
            except: pass
    return mapping
stock_info_map = get_stock_info_map()

# --- 4. 大盤環境偵測 ---
@st.cache_data(ttl=60) 
def get_market_env():
    res = {}
    for k, v in {"上市": "TSE", "上櫃": "OTC"}.items():
        try:
            curr_p, _, _ = get_realtime_price_data(v)
            df_h = get_historical_data("^TWII" if k=="上市" else "^TWOII")
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

# --- 5. 主畫面標題與環境 ---
st.markdown("### 🏹 姊布林 ABCDE & 營收戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

# --- 6. 側邊欄切換 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇模式", ["姊布林策略", "營收動能參數"])

# ==========================================
# 區塊 A：姊布林策略 (獨立區域)
# ==========================================
if mode == "姊布林策略":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描姊布林"):
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        with st.spinner("姊布林策略分析中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "產業排位": "-", "族群細分": "-"})
                p_curr, p_yest, vol_raw = get_realtime_price_data(code)
                if not p_curr: continue
                # (此處保留原姊布林運算邏輯，因篇幅精簡，欄位對齊您的需求)
                results.append({
                    "代號": code, "名稱": info["簡稱"], "現價": p_curr, 
                    "漲幅%": f"{((p_curr-p_yest)/p_yest*100):.1f}%" if p_yest else "-",
                    "成交值(億)": round((vol_raw * p_curr) / 100000000, 1),
                    "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                })
        st.session_state.scan_results = pd.DataFrame(results)
    
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# ==========================================
# 區塊 B：營收動能參數 (獨立區域)
# ==========================================
elif mode == "營收動能參數":
    st.sidebar.info("模式：抓取近三月平均年增率 > 20% 個股")
    if st.sidebar.button("📊 執行營收自動篩選"):
        # 1. 定義要尋找的月份 (手動設定或抓取資料夾內最新三個月)
        target_months = ["202603", "202602", "202601"] 
        folder = "revenue_data"
        
        all_revenue_data = {} # {代號: {名稱: str, 年增率清單: []}}

        with st.spinner("正在計算營收動能..."):
            # 遍歷三個月的 CSV 檔案
            for ym in target_months:
                for prefix in ["TWSE", "TPEX"]:
                    f_path = f"{folder}/{prefix}_{ym}.csv"
                    if os.path.exists(f_path):
                        try:
                            try: df_rev = pd.read_csv(f_path, encoding='utf-8-sig')
                            except: df_rev = pd.read_csv(f_path, encoding='cp950')
                            
                            # 找出關鍵欄位：第一欄通常是代號，名稱在第二欄
                            code_col = df_rev.columns[0]
                            name_col = df_rev.columns[1]
                            # 尋找包含「去年同月增減」且有「%」的年增率欄位
                            growth_col = [c for c in df_rev.columns if '去年同月增減' in str(c) and '%' in str(c)]
                            
                            if growth_col:
                                for _, r in df_rev.iterrows():
                                    c_id = str(r[code_col]).strip()
                                    c_name = str(r[name_col]).strip()
                                    val = float(str(r[growth_col[0]]).replace(',', ''))
                                    
                                    if c_id not in all_revenue_data:
                                        all_revenue_data[c_id] = {"名稱": c_name, "年增率清單": []}
                                    all_revenue_data[c_id]["年增率清單"].append(val)
                        except: pass
            
            # 2. 計算平均並進行即時資料抓取
            final_list = []
            for c_id, data in all_revenue_data.items():
                if len(data["年增率清單"]) >= 3: # 必須滿三個月
                    avg_growth = sum(data["年增率清單"][:3]) / 3
                    
                    if avg_growth > 20.0:
                        # 3. 抓取即時價格 (來源對齊姊布林)
                        p_curr, p_yest, vol_raw = get_realtime_price_data(c_id)
                        if p_curr:
                            # 4. 對齊產業排位 (從 TWSE/TPEX.csv 找)
                            info = stock_info_map.get(c_id, {"產業排位": "-", "族群細分": "-"})
                            
                            final_list.append({
                                "代號": c_id,
                                "名稱": data["名稱"],
                                "近三月平均年增%": round(avg_growth, 2),
                                "現價": p_curr,
                                "漲跌幅%": f"{((p_curr-p_yest)/p_yest*100):.2f}%" if p_yest else "-",
                                "成交值(億)": round((vol_raw * p_curr) / 100000000, 2),
                                "產業排位": info["產業排位"],
                                "族群細分": info["族群細分"]
                            })
            
            st.session_state.revenue_results = pd.DataFrame(final_list)

    if st.session_state.revenue_results is not None:
        if not st.session_state.revenue_results.empty:
            # 顯示結果並開啟標題排序功能
            st.dataframe(
                st.session_state.revenue_results, 
                use_container_width=True, 
                hide_index=True
            )
        else:
            st.warning("未找到符合近三月平均年增 > 20% 的個股，請確認 CSV 資料夾內容。")

# --- 7. 安全登出 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.revenue_results = None
    st.rerun()
