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
                            "產業排位": str(row.iloc[2]).strip() if len(row) >
