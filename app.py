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

# --- 0.1 🏎️ 歷史數據快取 (提升搜尋速度) ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

# --- 1. 網頁配置與背景設置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
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

# ============================================================================
# 【區塊 A：營收動能策略 - 獨立區塊開始】
# ============================================================================

# --- A-1. TWSE 營收資料讀取與清洗函數 ---
@st.cache_data(ttl=3600)
def get_twse_revenue_data_cleaned():
    """
    從 revenue_data 資料夾讀取最新 3 個月的 TWSE CSV 檔案
    清洗欄位保留：資料年月、公司代號、公司名稱、去年同月增減(%)
    回傳：清洗後的 TWSE DataFrame
    """
    revenue_data = []
    
    if not os.path.exists("revenue_data"):
        return pd.DataFrame()
    
    # 取得 revenue_data 資料夾中所有 TWSE 檔案（最新 3 個月）
    files = os.listdir("revenue_data")
    twse_files = sorted([f for f in files if f.startswith("TWSE_") and f.endswith(".csv")], reverse=True)[:3]
    
    for file_name in twse_files:
        file_path = os.path.join("revenue_data", file_name)
        try:
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            except:
                df = pd.read_csv(file_path, encoding='cp950')
            
            # 欄位清洗：只保留必要欄位
            required_cols = ['資料年月', '公司代號', '公司名稱', '去年同月增減(%)']
            
            # 嘗試匹配欄位（處理可能的空格或變體）
            df.columns = df.columns.str.strip()
            available_cols = [col for col in required_cols if col in df.columns]
            
            if len(available_cols) == 4:
                df_clean = df[required_cols].copy()
                df_clean = df_clean.fillna(0)
                df_clean['去年同月增減(%)'] = pd.to_numeric(df_clean['去年同月增減(%)'], errors='coerce').fillna(0)
                revenue_data.append(df_clean)
        except Exception as e:
            pass
    
    if revenue_data:
        df_combined = pd.concat(revenue_data, ignore_index=True)
        return df_combined
    else:
        return pd.DataFrame()

# --- A-2. TPEX 營收資料讀取與清洗函數 ---
@st.cache_data(ttl=3600)
def get_tpex_revenue_data_cleaned():
    """
    從 revenue_data 資料夾讀取最新 3 個月的 TPEX CSV 檔案
    清洗欄位保留：資料年月、公司代號、公司名稱、去年同月增減(%)
    回傳：清洗後的 TPEX DataFrame
    """
    revenue_data = []
    
    if not os.path.exists("revenue_data"):
        return pd.DataFrame()
    
    # 取得 revenue_data 資料夾中所有 TPEX 檔案（最新 3 個月）
    files = os.listdir("revenue_data")
    tpex_files = sorted([f for f in files if f.startswith("TPEX_") and f.endswith(".csv")], reverse=True)[:3]
    
    for file_name in tpex_files:
        file_path = os.path.join("revenue_data", file_name)
        try:
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig')
            except:
                df = pd.read_csv(file_path, encoding='cp950')
            
            # 欄位清洗：只保留必要欄位
            required_cols = ['資料年月', '公司代號', '公司名稱', '去年同月增減(%)']
            
            # 嘗試匹配欄位（處理可能的空格或變體）
            df.columns = df.columns.str.strip()
            available_cols = [col for col in required_cols if col in df.columns]
            
            if len(available_cols) == 4:
                df_clean = df[required_cols].copy()
                df_clean = df_clean.fillna(0)
                df_clean['去年同月增減(%)'] = pd.to_numeric(df_clean['去年同月增減(%)'], errors='coerce').fillna(0)
                revenue_data.append(df_clean)
        except Exception as e:
            pass
    
    if revenue_data:
        df_combined = pd.concat(revenue_data, ignore_index=True)
        return df_combined
    else:
        return pd.DataFrame()

# --- A-3. 篩選 TWSE 營收動能函數 ---
def filter_twse_revenue_momentum():
    """
    【步驟 1】TWSE 獨立計算：
    - 合併 TWSE 近 3 個月資料
    - 計算每個股票的平均年增率
    - 篩選近三月平均年增率 > 20% 的個股
    回傳：代號、名稱、近三月平均年增%（TWSE 專用）
    """
    df_twse = get_twse_revenue_data_cleaned()
    
    if df_twse.empty:
        return pd.DataFrame()
    
    # 計算每個股票的平均年增率
    df_agg = df_twse.groupby(['公司代號', '公司名稱']).agg({
        '去年同月增減(%)': 'mean'
    }).reset_index()
    
    df_agg.columns = ['代號', '名稱', '近三月平均年增%']
    
    # 篩選近三月平均年增率 > 20%
    df_filtered = df_agg[df_agg['近三月平均年增%'] > 20].copy()
    
    return df_filtered

# --- A-4. 篩選 TPEX 營收動能函數 ---
def filter_tpex_revenue_momentum():
    """
    【步驟 2】TPEX 獨立計算：
    - 合併 TPEX 近 3 個月資料
    - 計算每個股票的平均年增率
    - 篩選近三月平均年增率 > 20% 的個股
    回傳：代號、名稱、近三月平均年增%（TPEX 專用）
    """
    df_tpex = get_tpex_revenue_data_cleaned()
    
    if df_tpex.empty:
        return pd.DataFrame()
    
    # 計算每個股票的平均年增率
    df_agg = df_tpex.groupby(['公司代號', '公司名稱']).agg({
        '去年同月增減(%)': 'mean'
    }).reset_index()
    
    df_agg.columns = ['代號', '名稱', '近三月平均年增%']
    
    # 篩選近三月平均年增率 > 20%
    df_filtered = df_agg[df_agg['近三月平均年增%'] > 20].copy()
    
    return df_filtered

# --- A-5. 營收動能結果組合函數 ---
def build_revenue_momentum_results():
    """
    【步驟 3】合併結果：
    - 取得 TWSE 篩選結果
    - 取得 TPEX 篩選結果
    - 合併兩者
    - 為每一個個股補充：現價、漲幅%、成交值(億)、產業排位、族群細分
    回傳：完整結果表 (市場別、代號、名稱、近三月平均年增%、現價、漲幅%、成交值(億)、產業排位、族群細分)
    """
    # 步驟 1: TWSE 獨立篩選
    df_twse_filtered = filter_twse_revenue_momentum()
    if not df_twse_filtered.empty:
        df_twse_filtered.insert(0, '市場別', '上市')
    
    # 步驟 2: TPEX 獨立篩選
    df_tpex_filtered = filter_tpex_revenue_momentum()
    if not df_tpex_filtered.empty:
        df_tpex_filtered.insert(0, '市場別', '上櫃')
    
    # 步驟 3: 合併 TWSE + TPEX 結果
    df_momentum = pd.concat([df_twse_filtered, df_tpex_filtered], ignore_index=True)
    
    if df_momentum.empty:
        return pd.DataFrame()
    
    results = []
    
    with st.spinner("分析營收動能中..."):
        for _, row in df_momentum.iterrows():
            market = row['市場別']
            code = row['代號']
            name = row['名稱']
            avg_revenue_growth = row['近三月平均年增%']
            
            # --- A-5-1. 營收動能區塊：獲取即時價格 ---
            p_curr = get_realtime_price(code)
            if not p_curr:
                continue
            
            # --- A-5-2. 營收動能區塊：獲取歷史數據計算漲幅% 與 成交值(億) ---
            df_hist = None
            if market == '上市':
                df_hist = get_historical_data(f"{code}.TW")
            elif market == '上櫃':
                df_hist = get_historical_data(f"{code}.TWO")
            
            if df_hist is None or df_hist.empty or len(df_hist) < 2:
                continue
            
            if isinstance(df_hist.columns, pd.MultiIndex):
                df_hist.columns = df_hist.columns.get_level_values(0)
            
            df_hist = df_hist.dropna(subset=['Close'])
            
            if len(df_hist) < 2:
                continue
            
            # 計算漲幅%
            today_date = datetime.now().date()
            if df_hist.index[-1].date() >= today_date:
                p_yest = float(df_hist['Close'].iloc[-2])
            else:
                p_yest = float(df_hist['Close'].iloc[-1])
            
            chg = (p_curr - p_yest) / p_yest if p_yest != 0 else 0
            
            # 計算成交值(億)
            if len(df_hist) > 0 and df_hist.index[-1].date() >= today_date:
                vol_amt = (df_hist['Volume'].iloc[-1] * p_curr) / 100000000
            else:
                vol_amt = 0
            
            # --- A-5-3. 營收動能區塊：取得產業排位與族群細分 ---
            industry_rank = "-"
            industry_group = "-"
            
            info = stock_info_map.get(code)
            if info:
                industry_rank = info.get("產業排位", "-")
                industry_group = info.get("族群細分", "-")
            
            results.append({
                "市場別": market,
                "代號": code,
                "名稱": name,
                "近三月平均年增%": f"{avg_revenue_growth:.2f}%",
                "現價": p_curr,
                "漲幅%": f"{chg*100:.1f}%",
                "成交值(億)": round(vol_amt, 1),
                "產業排位": industry_rank,
                "族群細分": industry_group
            })
    
    if results:
        return pd.DataFrame(results)
    else:
        return pd.DataFrame()

# ============================================================================
# 【區塊 A：營收動能策略 - 獨立區塊結束】
# ============================================================================

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室 (即時優化版)")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}** (加權總控機制已啟動)")

# --- 6. 側邊欄與切換模式 ---
st.sidebar.title("🛠️ 設定區")
strategy_mode = st.sidebar.radio("📊 策略模式選擇", ["🏹 姊布林 ABCDE 策略", "💰 營收動能策略"])

# ============================================================================
# 【區塊 B：姊布林 ABCDE 策略 - 獨立區塊開始】
# ============================================================================

if strategy_mode == "🏹 姊布林 ABCDE 策略":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)

    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        
        # 【總司令官判斷】
        main_market_light = m_env['上市']['燈號']
        
        with st.spinner("分析環境中..."):
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
                    
                    # 判定個股市場環境
                    current_env = m_env[m_type]
                    
                    today_date = datetime.now().date()
                    if df.index[-1].date() >= today_date:
                        p_yest = float(df['Close'].iloc[-2])
                        history_for_ma = df['Close'].iloc[-20:-1].tolist()
                    else:
                        p_yest = float(df['Close'].iloc[-1])
                        history_for_ma = df['Close'].iloc[-19:].tolist()
                    
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
                        # --- 🌟 修正核心：加權總控判定 ---
                        if "🔴 紅燈" in main_market_light:
                            # 狀況 A：加權紅燈 -> 全市場進入最高防禦，僅限 A、B
                            if 0.05 <= bw <= 0.1 and 0.03 <= chg <= 0.07: res_tag = "🔥【A：潛龍】"
                            elif 0.1 < bw <= 0.2 and 0.03 <= chg <= 0.05: res_tag = "🎯【B：海龍】"
                            else: res_tag = "⚪ 參數不符(大盤紅燈限AB)"
                        else:
                            # 狀況 B：加權綠/黃燈 -> 依照個股所屬市場燈號執行
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
                        "產業排位": info["產業排位"], "2026指標": info["實力指標"],
                        "族群細分": info["族群細分"], "關鍵技術": info["關鍵技術"]
                    })
            if results:
                st.session_state.scan_results = pd.DataFrame(results)

    # --- 7. 顯示姊布林結果 ---
    st.markdown("#### 🏹 姊布林 ABCDE 策略結果")
    if st.session_state.scan_results is not None:
        st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

# ============================================================================
# 【區塊 B：姊布林 ABCDE 策略 - 獨立區塊結束】
# ============================================================================

# ============================================================================
# 【區塊 C：營收動能策略 - 顯示區塊開始】
# ============================================================================

elif strategy_mode == "💰 營收動能策略":
    if st.sidebar.button("🚀 開始掃描營收動能"):
        st.session_state.revenue_results = build_revenue_momentum_results()

    # --- 7. 顯示營收動能結果 ---
    st.markdown("#### 💰 營收動能策略結果")
    st.markdown("""
    **計算邏輯：**
    1️⃣ TWSE 近 3 個月資料合併 → 計算平均年增率 > 20% 
    2️⃣ TPEX 近 3 個月資料合併 → 計算平均年增率 > 20%
    3️⃣ 合併上述結果，補充現價、漲幅、成交值、產業資訊
    """)
    
    if st.session_state.revenue_results is not None and not st.session_state.revenue_results.empty:
        st.dataframe(
            st.session_state.revenue_results,
            use_container_width=True,
            hide_index=True
        )
    elif st.session_state.revenue_results is not None and st.session_state.revenue_results.empty:
        st.warning("⚠️ 未發現符合條件的營收動能個股 (近三月平均年增% > 20%)")
        st.info("💡 檢查項目：\n- revenue_data 資料夾中是否有 TWSE_202603... 與 TPEX_202603... 的 CSV 檔\n- CSV 欄位是否包含：資料年月、公司代號、公司名稱、去年同月增減(%)")
    else:
        st.info("💡 點擊左側 '開始掃描營收動能' 按鈕以獲取結果")

# ============================================================================
# 【區塊 C：營收動能策略 - 顯示區塊結束】
# ============================================================================

# --- 登出按鈕 ---
if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.session_state.revenue_results = None
    st.rerun()
