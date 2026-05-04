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

# --- 0. 基礎函數與即時價格 ---
def get_realtime_price(stock_id):
    if stock_id == 'OTC': target = '%5ETWOII'
    elif stock_id == 'TSE': target = '%5ETWII'
    else: target = stock_id
    url = f"https://tw.stock.yahoo.com/quote/{target}"
    headers = {'User-Agent': 'Mozilla/5.0'}
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

# --- 1. 營收數據核心處理模組 (修正區) ---
def clean_revenue_column_value(val):
    """清理營收增減值，處理 %, 逗號與非數值字串"""
    if pd.isna(val) or val == '-': return 0.0
    val_str = str(val).replace('%', '').replace(',', '').strip()
    try:
        return float(val_str)
    except:
        return 0.0

@st.cache_data(ttl=3600)
def get_cleaned_revenue_data(market_type="TWSE"):
    """
    整合 TWSE/TPEX 讀取邏輯並強化欄位辨識
    """
    path = "revenue_data"
    if not os.path.exists(path): return pd.DataFrame()
    
    prefix = "TWSE_" if market_type == "TWSE" else "TPEX_"
    files = sorted([f for f in os.listdir(path) if f.startswith(prefix) and f.endswith(".csv")], reverse=True)[:3]
    
    combined_list = []
    for f in files:
        f_path = os.path.join(path, f)
        try:
            # 優先嘗試 utf-8-sig (處理 BOM), 失敗則用 cp950
            try: df = pd.read_csv(f_path, encoding='utf-8-sig')
            except: df = pd.read_csv(f_path, encoding='cp950')
            
            df.columns = df.columns.str.strip().str.replace('"', '')
            
            # 找出營收年增率欄位 (YoY)
            yoy_col = next((c for c in df.columns if "去年同月" in c and "增減" in c), None)
            id_col = next((c for c in df.columns if "代號" in c or "公司代號" in c), None)
            name_col = next((c for c in df.columns if "名稱" in c or "公司名稱" in c), None)
            
            if yoy_col and id_col:
                df_sub = df[[id_col, name_col, yoy_col]].copy()
                df_sub.columns = ['代號', '名稱', 'YoY']
                df_sub['代號'] = df_sub['代號'].astype(str).str.strip()
                df_sub['YoY'] = df_sub['YoY'].apply(clean_revenue_column_value)
                combined_list.append(df_sub)
        except Exception as e:
            st.error(f"讀取 {f} 失敗: {e}")
            
    return pd.concat(combined_list) if combined_list else pd.DataFrame()

def build_revenue_momentum_results():
    """計算近三月平均 YoY > 20%"""
    with st.spinner("🔍 正在計算近三月營收動能..."):
        # 抓取並合併上市櫃數據
        df_all = pd.concat([get_cleaned_revenue_data("TWSE"), get_cleaned_revenue_data("TPEX")])
        
        if df_all.empty: return pd.DataFrame()
        
        # 核心邏輯：計算算術平均 (YoY 均值)
        df_agg = df_all.groupby(['代號', '名稱'])['YoY'].mean().reset_index()
        df_agg = df_agg[df_agg['YoY'] > 20].copy() # 篩選門檻
        
        results = []
        for _, row in df_agg.iterrows():
            code = row['代號']
            # 判定市場別供 yfinance 使用
            market_suffix = ".TW" 
            # 這裡可加入邏輯判斷是否為 OTC，或直接嘗試 download
            p_curr = get_realtime_price(code)
            if not p_curr: continue
            
            # 獲取資訊 (省略部分與你原始碼相同的 yf 抓取邏輯以保持精簡)
            results.append({
                "代號": code,
                "名稱": row['名稱'],
                "近三月平均年增%": f"{row['YoY']:.2f}%",
                "現價": p_curr
            })
            
        return pd.DataFrame(results)

# --- 2. Streamlit UI 整合 (其餘 UI 代碼保持不變) ---
# ... (此處保留你原有的 UI、密碼鎖與側邊欄邏輯) ...
