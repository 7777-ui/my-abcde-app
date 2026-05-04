import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import base64
import pytz
import requests
import numpy as np
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 基礎配置與 UI 設定 ---
st.set_page_config(page_title="🏹 戰情室 | 姊布林與營收動能", page_icon="🏹", layout="wide")
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
    .stDataFrame {{ background-color: rgba(20, 20, 20, 0.8) !important; border-radius: 10px; padding: 5px; }}
    </style>
    """
    st.markdown(style, unsafe_allow_html=True)
set_ui_cleanup("header_image.png")

# --- 0.1 密碼鎖 ---
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

# --- 1. 通用組件與數據抓取 (Shared Components) ---
def get_realtime_price(target):
    # 支援代號與大盤
    if target == 'OTC': target = '%5ETWOII'
    elif target == 'TSE': target = '%5ETWII'
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0...'}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        match = re.search(r'"regularMarketPrice":\s*([0-9.]+)', response.text)
        if match: return float(match.group(1).replace(',', ''))
    except: pass
    return None

@st.cache_data(ttl=604800)
def get_basic_info_map():
    mapping = {}
    for f_name in ["TWSE.csv", "TPEX.csv"]:
        if os.path.exists(f_name):
            try:
                df = pd.read_csv(f_name, encoding='utf-8-sig').fillna('-')
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

# --- 2. 營收動能策略區塊 (Revenue Momentum Strategy) ---
def process_revenue_momentum():
    folder = "revenue_data"
    if not os.path.exists(folder):
        st.error(f"找不到 {folder} 資料夾")
        return pd.DataFrame()

    all_files = os.listdir(folder)
    
    def get_latest_3_merged(prefix):
        files = sorted([f for f in all_files if f.startswith(prefix)], reverse=True)[:3]
        df_list = []
        for f in files:
            path = os.path.join(folder, f)
            try:
                # 欄位強制提取：資料年月、公司代號、公司名稱、營業收入-去年同月增減(%)
                temp_df = pd.read_csv(path, encoding='utf-8-sig')
                target_cols = ['資料年月', '公司代號', '公司名稱', '營業收入-去年同月增減(%)']
                # 處理欄位名稱不完全一致的可能性
                temp_df.columns = [c.strip() for c in temp_df.columns]
                filtered_df = temp_df[target_cols].copy()
                filtered_df['公司代號'] = filtered_df['公司代號'].astype(str).str.strip()
                df_list.append(filtered_df)
            except Exception as e:
                st.warning(f"檔案 {f} 讀取失敗: {e}")
        
        if not df_list: return pd.DataFrame()
        
        combined = pd.concat(df_list)
        # 計算近三月平均年增率
        avg_revenue = combined.groupby(['公司代號', '公司名稱'])['營業收入-去年同月增減(%)'].mean().reset_index()
        avg_revenue.columns = ['代號', '名稱', '近三月平均年增%']
        return avg_revenue[avg_revenue['近三月平均年增%'] > 20]

    # 第一、二步驟
    twse_top = get_latest_3_merged("TWSE")
    twse_top['市場別'] = '上市'
    tpex_top = get_latest_3_merged("TPEX")
    tpex_top['市場別'] = '上櫃'
    
    # 第三步驟：合併結果並對齊即時數據
    final_momentum = pd.concat([twse_top, tpex_top], ignore_index=True)
    info_map = get_basic_info_map()
    
    res_list = []
    for _, row in final_momentum.iterrows():
        code = row['代號']
        p_curr = get_realtime_price(code)
        if not p_curr: continue
        
        # 取得昨收計算漲幅 (簡單化處理)
        hist = yf.download(f"{code}.TW" if row['市場別']=='上市' else f"{code}.TWO", period="2d", progress=False)
        chg_pct = 0.0
        if not hist.empty and len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            chg_pct = ((p_curr - prev_close) / prev_close) * 100
            vol_amt = (hist['Volume'].iloc[-1] * p_curr) / 100000000
        else: vol_amt = 0.0

        res_list.append({
            "市場別": row['市場別'],
            "代號": code,
            "名稱": row['名稱'],
            "近三月平均年增%": round(row['近三月平均年增%'], 2),
            "現價": p_curr,
            "漲幅%": f"{chg_pct:.2f}%",
            "成交值(億)": round(vol_amt, 2),
            "產業排位": info_map.get(code, {}).get("產業排位", "-"),
            "族群細分": info_map.get(code, {}).get("族群細分", "-")
        })
    return pd.DataFrame(res_list)

# --- 3. 姊布林策略區塊 (Bollinger Strategy) ---
# (此處保留妳原本的姊布林邏輯，僅將資料來源與營收動能區分開)
def process_bollinger_strategy(raw_codes):
    # 原有的姊布林邏輯代碼...
    # [此處省略以節省空間，但實作時需包含原有的 get_market_env 等判定]
    pass

# --- 4. 主介面邏輯 ---
st.sidebar.title("🛠️ 策略切換")
mode = st.sidebar.radio("請選擇操作模式", ["🏹 姊布林戰情", "📊 營收動能戰情"])

if mode == "📊 營收動能戰情":
    st.subheader("🔥 近三月營收連續成長動能榜 (>20%)")
    if st.button("🚀 執行營收掃描"):
        with st.spinner("正在計算近三月營收平均值..."):
            df_momentum = process_revenue_momentum()
            if not df_momentum.empty:
                st.dataframe(df_momentum.sort_values("近三月平均年增%", ascending=False), 
                             use_container_width=True, hide_index=True)
            else:
                st.info("目前沒有符合近三月平均年增 > 20% 的個股。")

elif mode == "🏹 姊布林戰情":
    # 這裡放置妳原始的姊布林 UI 與執行代碼
    st.subheader("🏹 姊布林 ABCDE 策略")
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描"):
        # 執行原本的 scan 邏輯...
        pass
