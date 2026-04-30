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

# --- 0. 🚀 即時數據抓取函數 (🛠️ /optimize: 加入即時價格快取) ---
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

# --- 0.1 🏎️ 歷史數據快取 ---
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

# --- 5. 主畫面 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
m_col1, m_col2 = st.columns(2)
with m_col1: st.metric(f"加權指數 ({m_env['上市']['價格']:,.2f})", m_env['上市']['燈號'], f"帶寬: {m_env['上市']['帶寬']:.2%}")
with m_col2: st.metric(f"OTC 指數 ({m_env['上櫃']['價格']:,.2f})", m_env['上櫃']['燈號'], f"帶寬: {m_env['上櫃']['帶寬']:.2%}")

tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

# --- 6. 側邊欄設定 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

# --- 7. 姊布林 ABCDE 策略邏輯 ---
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        codes = re.findall(r'\b\d{4,6}\b', raw_input)
        results = []
        main_market_light = m_env['上市']['燈號']
        
        with st.spinner("分析環境中..."):
            for code in codes:
                info = stock_info_map.get(code, {"簡稱": f"台股{code}", "市場": "未知", "產業排位": "-", "實力指標": "-", "族群細分": "-", "關鍵技術": "-"})
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
                        "市場": m_type,
                        "代號": code, "名稱": info["簡稱"], "策略": res_tag,
                        "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", "成交值(億)": round(vol_amt, 1),
                        "個股帶寬%": f"{bw*100:.2f}%", "比值": round(ratio, 2),
                        "產業排位": info["產業排位"], "2026指標": info["實力指標"],
                        "族群細分": info["族群細分"], "關鍵技術": info["關鍵技術"]
                    })
        if results:
            st.session_state.scan_results = pd.DataFrame(results)

# --- 8. 營收動能策略邏輯 (🛠️ 已修改：雙資料夾分流 + 檔名倒序抓取) ---
elif mode == "營收動能策略":
    st.sidebar.info("💡 偵測 `revenue_data_TWSE/` 與 `revenue_data_TPEX/` 檔名倒序最新三月資料。")
    if st.sidebar.button("📊 啟動營收動能分析"):
        
        # 定義兩個資料夾與對應後綴
        market_configs = [
            {"folder": "revenue_data_TWSE", "suffix": ".TW", "label": "上市"},
            {"folder": "revenue_data_TPEX", "suffix": ".TWO", "label": "上櫃"}
        ]
        
        all_final_targets = [] # 用來存放兩邊篩選出來的 targets

        for config in market_configs:
            folder = config["folder"]
            if not os.path.exists(folder):
                st.warning(f"⚠️ 找不到資料夾: {folder}")
                continue
                
            # 關鍵修正：改用檔名倒序 (reverse=True)，確保日期大的排前面
            all_files = glob.glob(os.path.join(folder, "*.csv"))
            all_files.sort(reverse=True) 
            
            if len(all_files) < 3:
                st.warning(f"⚠️ {folder} 內檔案不足 3 份，跳過分析。")
                continue
                
            recent_files = all_files[:3]
            month_dfs = []
            
            # 讀取並計算該市場的近三月資料
            for f in recent_files:
                try:
                    try: t_df = pd.read_csv(f, encoding='utf-8-sig')
                    except: t_df = pd.read_csv(f, encoding='cp950')
                    
                    t_df.columns = [c.strip() for c in t_df.columns]
                    col_code, col_name = '公司代號', '公司名稱'
                    col_rev_now, col_rev_last = '營業收入-當月營收', '營業收入-去年當月營收'
                    
                    if all(col in t_df.columns for col in [col_code, col_rev_now, col_rev_last]):
                        t_df[col_code] = t_df[col_code].astype(str).str.strip()
                        for col in [col_rev_now, col_rev_last]:
                            t_df[col] = pd.to_numeric(t_df[col].astype(str).str.replace(',', ''), errors='coerce')
                        
                        t_df = t_df.dropna(subset=[col_code, col_rev_now, col_rev_last])
                        t_df['yoy'] = (t_df[col_rev_now] - t_df[col_rev_last]) / t_df[col_rev_last]
                        month_dfs.append(t_df[[col_code, col_name, 'yoy']])
                except:
                    continue

            # 進行三月合併與篩選
            if len(month_dfs) == 3:
                m1, m2, m3 = [df.drop_duplicates('公司代號') for df in month_dfs]
                merged = m1.rename(columns={'yoy': 'yoy1'})
                merged = merged.merge(m2[['公司代號', 'yoy']].rename(columns={'yoy': 'yoy2'}), on='公司代號')
                merged = merged.merge(m3[['公司代號', 'yoy']].rename(columns={'yoy': 'yoy3'}), on='公司代號')
                
                merged['avg_growth'] = (merged['yoy1'] + merged['yoy2'] + merged['yoy3']) / 3 * 100
                targets = merged[merged['avg_growth'] > 20].copy()
                targets['市場別'] = config["label"]
                targets['後綴'] = config["suffix"]
                all_final_targets.append(targets)

        # --- 整合輸出 ---
        if not all_final_targets:
            st.info("目前兩大資料夾中無符合平均年增率 > 20% 的公司。")
        else:
            final_df = pd.concat(all_final_targets, ignore_index=True)
            rev_results = []
            
            with st.spinner(f"正在抓取 {len(final_df)} 檔股票之即時價格與成交量..."):
                for _, row in final_df.iterrows():
                    code = row['公司代號']
                    info = stock_info_map.get(code, {"市場": row['市場別'], "產業排位": "-", "族群細分": "-"})
                    p_curr = get_realtime_price(code)
                    if not p_curr: continue
                    
                    # 使用預設好的後綴抓取歷史資料
                    df_h = get_historical_data(f"{code}{row['後綴']}")
                    
                    if not df_h.empty:
                        if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                        p_yest = float(df_h['Close'].iloc[-1])
                        chg = (p_curr - p_yest) / p_yest
                        vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                        
                        rev_results.append({
                            "市場": row['市場別'],
                            "代號": code, "名稱": row['公司名稱'], 
                            "三月均年增%": f"{row['avg_growth']:.1f}%",
                            "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", 
                            "成交值(億)": round(vol_amt, 1),
                            "產業排位": info["產業排位"], "族群細分": info["族群細分"]
                        })
            
            if rev_results:
                st.session_state.scan_results = pd.DataFrame(rev_results)

# --- 9. 顯示結果 ---
if st.session_state.scan_results is not None:
    st.markdown("### 📊 掃描結果清單")
    cols = st.session_state.scan_results.columns.tolist()
    if "市場" in cols:
        cols.insert(0, cols.pop(cols.index("市場")))
        st.session_state.scan_results = st.session_state.scan_results[cols]
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
