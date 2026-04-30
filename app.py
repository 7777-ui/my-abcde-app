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

# --- 1. 網頁配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", page_icon="🏹", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

if "scan_results" not in st.session_state:
    st.session_state.scan_results = None

# --- 2. 🔐 密碼鎖 (密碼: test0403) ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密密碼", type="password")
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

# --- 5. 主畫面與側邊欄 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
tw_tz = pytz.timezone('Asia/Taipei')
st.write(f"📅 **數據更新時間：{datetime.now(tw_tz).strftime('%Y/%m/%d %H:%M:%S')}**")

st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

# --- 8. 營收動能策略邏輯 (🛠️ /refactor: 雙資料夾獨立排序合併) ---
if mode == "營收動能策略":
    st.sidebar.info("💡 獨立從 TWSE 與 TPEX 資料夾抓取最新三月資料。")
    if st.sidebar.button("📊 啟動營收動能分析"):
        
        final_targets = []
        # 定義資料夾與市場標記
        folder_configs = [
            ("revenue_data_TWSE", "上市"),
            ("revenue_data_TPEX", "上櫃")
        ]

        with st.spinner("正在進行跨市場營收分析..."):
            for folder, m_label in folder_configs:
                if not os.path.exists(folder):
                    st.error(f"找不到資料夾: {folder}")
                    continue
                
                # 2-1. 檔名倒序抓取 CSV
                all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
                
                if len(all_files) < 3:
                    st.warning(f"⚠️ {m_label} 資料夾檔案不足 3 份，跳過此市場。")
                    continue
                
                recent_files = all_files[:3]
                month_dfs = []
                
                for f in recent_files:
                    try:
                        try: t_df = pd.read_csv(f, encoding='utf-8-sig')
                        except: t_df = pd.read_csv(f, encoding='cp950')
                        
                        t_df.columns = [c.strip() for c in t_df.columns]
                        # 欄位定義
                        col_code = '公司代號'
                        col_name = '公司名稱'
                        col_rev_now = '營業收入-當月營收'
                        col_rev_last = '營業收入-去年當月營收'
                        
                        if all(col in t_df.columns for col in [col_code, col_rev_now, col_rev_last]):
                            t_df[col_code] = t_df[col_code].astype(str).str.strip()
                            for col in [col_rev_now, col_rev_last]:
                                t_df[col] = pd.to_numeric(t_df[col].astype(str).str.replace(',', ''), errors='coerce')
                            
                            t_df = t_df.dropna(subset=[col_code, col_rev_now, col_rev_last])
                            # 計算 YoY
                            t_df['yoy'] = (t_df[col_rev_now] - t_df[col_rev_last]) / t_df[col_rev_last]
                            month_dfs.append(t_df[[col_code, col_name, 'yoy']])
                    except: continue

                if len(month_dfs) == 3:
                    # 合併與計算
                    m1, m2, m3 = [d.drop_duplicates('公司代號') for d in month_dfs]
                    merged = m1.rename(columns={'yoy': 'yoy1'})
                    merged = merged.merge(m2[['公司代號', 'yoy']].rename(columns={'yoy': 'yoy2'}), on='公司代號')
                    merged = merged.merge(m3[['公司代號', 'yoy']].rename(columns={'yoy': 'yoy3'}), on='公司代號')
                    
                    # 算平均年增率
                    merged['avg_growth'] = (merged['yoy1'] + merged['yoy2'] + merged['yoy3']) / 3 * 100
                    
                    # 篩選 > 20%
                    targets = merged[merged['avg_growth'] > 20].copy()
                    
                    for _, row in targets.iterrows():
                        code = row['公司代號']
                        info = stock_info_map.get(code, {"市場": m_label, "產業排位": "-", "族群細分": "-"})
                        p_curr = get_realtime_price(code)
                        if not p_curr: continue
                        
                        # 抓取歷史數據計算漲幅與成交量
                        suffix = ".TW" if m_label == "上市" else ".TWO"
                        df_h = get_historical_data(f"{code}{suffix}")
                        
                        if not df_h.empty:
                            if isinstance(df_h.columns, pd.MultiIndex): df_h.columns = df_h.columns.get_level_values(0)
                            p_yest = float(df_h['Close'].iloc[-1])
                            chg = (p_curr - p_yest) / p_yest
                            vol_amt = (df_h['Volume'].iloc[-1] * p_curr) / 100000000
                            
                            final_targets.append({
                                "市場": m_label,
                                "代號": code, "名稱": row['公司名稱'], 
                                "三月均年增%": f"{row['avg_growth']:.1f}%",
                                "現價": p_curr, "漲幅%": f"{chg*100:.1f}%", 
                                "成交值(億)": round(vol_amt, 1),
                                "產業排位": info.get("產業排位", "-"), 
                                "族群細分": info.get("族群細分", "-")
                            })

            if final_targets:
                st.session_state.scan_results = pd.DataFrame(final_targets)
            else:
                st.info("查無符合條件之個股。")

# --- 9. 顯示結果 ---
if st.session_state.scan_results is not None:
    st.markdown("### 📊 營收動能掃描結果")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
