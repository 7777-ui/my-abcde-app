import streamlit as st
import yfinance as yf
import pandas as pd
import re
import os
import pytz
from datetime import datetime
from streamlit_autorefresh import st_autorefresh

# --- 0. 基礎配置 ---
st.set_page_config(page_title="🏹 姊布林ABCDE 戰情室", layout="wide")
st_autorefresh(interval=180000, key="datarefresh")

# --- 1. 初始化 Session State ---
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

# --- 2. 登入邏輯 (必須最先執行) ---
if not st.session_state.password_correct:
    st.markdown("## 🔒 私人戰情室登入")
    pwd = st.text_input("請輸入密碼", type="password")
    if st.button("確認登入"):
        if pwd == "test0403":
            st.session_state.password_correct = True
            st.rerun()
        else:
            st.error("密碼錯誤")
    st.stop()

# --- 3. 核心功能與資料抓取 (這裡放 get_realtime_price, get_historical_data 等函數) ---
# ... (保留你之前的函數定義) ...

# --- 4. 側邊欄：定義變數 (修復 NameError 的關鍵) ---
st.sidebar.title("🛠️ 策略切換")

# 確保這行在所有的 if mode 判斷之前
mode = st.sidebar.radio("請選擇掃描模式：", ["姊布林 ABCDE", "營收動能策略"])

# --- 5. 主畫面與環境偵測 ---
st.markdown("### 🏹 姊布林 ABCDE 策略戰情室")
# (大盤燈號與環境偵測邏輯...)

# --- 6. 策略執行邏輯 ---

# 修正處：現在 mode 已經百分之百被定義了
if mode == "姊布林 ABCDE":
    raw_input = st.sidebar.text_area("輸入股票代碼", height=150)
    if st.sidebar.button("🚀 開始掃描戰情") and raw_input:
        # ... 執行的掃描邏輯 ...
        pass

elif mode == "營收動能策略":
    st.sidebar.info("💡 偵測 revenue_data 資料中...")
    if st.sidebar.button("📊 啟動營收動能分析"):
        # ... 執行的營收邏輯 ...
        pass

# --- 7. 顯示結果 ---
if st.session_state.scan_results is not None:
    st.markdown("### 📊 掃描結果清單")
    st.dataframe(st.session_state.scan_results, use_container_width=True, hide_index=True)

if st.sidebar.button("🔐 安全登出"):
    st.session_state.password_correct = False
    st.session_state.scan_results = None
    st.rerun()
