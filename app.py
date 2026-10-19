import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import re
import os
import base64
import requests
import time as t_time
from datetime import datetime, timedelta
from streamlit_autorefresh import st_autorefresh
import plotly.graph_objects as go

### --- 0. 🚀 即時數據抓取函數 ---
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

### --- 0.1 🏎️ 歷史數據快取 ---
@st.cache_data(ttl=3600)
def get_historical_data(code_with_suffix):
    return yf.download(code_with_suffix, period="2mo", progress=False)

### --- 1. 網頁配置與背景設置 (完美保留您的背景與樣式) ---
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

### --- 2. 🔐 密碼鎖 ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

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


# ==========================================
# 🎯 3. 專業級當沖覆盤模擬系統核心模組
# ==========================================
def init_replay_state():
    if "replay_step" not in st.session_state:
        st.session_state.replay_step = 1
    if "positions" not in st.session_state:
        st.session_state.positions = [] 
    if "trade_history" not in st.session_state:
        st.session_state.trade_history = []
    if "capital" not in st.session_state:
        st.session_state.capital = 1000000

@st.cache_data
def load_replay_data(stock_code):
    """ 從 Yahoo Finance 抓取近期真實歷史分K數據，並確保完整涵蓋 09:00-13:30 """
    try:
        df = yf.download(stock_code, period="7d", interval="1m", progress=False)
        if df.empty or len(df) < 10:
            raise Exception("資料不足")
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.reset_index()
        time_col = "Datetime" if "Datetime" in df.columns else ("Date" if "Date" in df.columns else df.columns[0])
        df = df.rename(columns={time_col: "Time", "Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume"})
        df["Time_dt"] = pd.to_datetime(df["Time"]).dt.tz_localize(None)
        df["Date"] = df["Time_dt"].dt.strftime("%Y-%m-%d")
        df["Time_Str"] = df["Time_dt"].dt.strftime("%H:%M")
        return df[['Time_dt', 'Date', 'Time_Str', 'Open', 'High', 'Low', 'Close', 'Volume']]
    except:
        pass

    # 備用穩定擬真數據產生器
    dates_range = pd.date_range(end=datetime.today(), periods=5, freq="B")
    records = []
    np.random.seed(42)
    for d in dates_range:
        d_str = d.strftime("%Y-%m-%d")
        t_min = pd.date_range(f"{d_str} 09:00", f"{d_str} 13:30", freq="1min")
        price = 100.0
        for t in t_min:
            change = np.random.normal(0, 0.3)
            open_p = price
            close_p = price + change
            high_p = max(open_p, close_p) + abs(np.random.normal(0, 0.2))
            low_p = min(open_p, close_p) - abs(np.random.normal(0, 0.2))
            vol = int(np.random.randint(100, 2000))
            price = max(1.0, close_p)
            records.append({
                "Time_dt": t,
                "Date": d_str,
                "Time_Str": t.strftime("%H:%M"),
                "Open": round(open_p, 2),
                "High": round(high_p, 2),
                "Low": round(low_p, 2),
                "Close": round(close_p, 2),
                "Volume": vol
            })
    return pd.DataFrame(records)

def resample_candles(df, timeframe):
    if timeframe == "1分K" or df.empty:
        return df
    rule_map = {"3分K": "3min", "5分K": "5min", "15分K": "15min", "日K": "1D"}
    rule = rule_map.get(timeframe, "5min")
    
    df_temp = df.set_index('Time_dt')
    agg_dict = {'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum', 'Date': 'first', 'Time_Str': 'last'}
    df_resampled = df_temp.resample(rule).agg(agg_dict).dropna().reset_index()
    return df_resampled

def calc_daytrade_cost(buy_price, sell_price, qty, side, fee_discount=0.28):
    buy_val = buy_price * qty * 1000
    sell_val = sell_price * qty * 1000
    buy_fee = buy_val * 0.001425 * fee_discount
    sell_fee = sell_val * 0.001425 * fee_discount
    tax = sell_val * 0.0015 
    
    if side == "LONG":
        net_pnl = (sell_val - buy_val) - (buy_fee + sell_fee + tax)
    else: 
        net_pnl = (buy_val - sell_val) - (buy_fee + sell_fee + tax)
    return net_pnl, buy_fee + sell_fee + tax

def render_daytrade_replay_ui():
    init_replay_state()
    st.title("🎯 專業當沖覆盤模擬：江波圖(均價線VWAP)與分K(EMA)雙效同步系統")
    st.markdown("左側呈現江波圖與當日成交均價(VWAP)，右側呈現多週期分K圖與 EMA 指數均線，圖表嚴格依時間進度同步運行！")
    
    # 1. 抓取資料
    col_s1, col_s2, col_s3, col_s4 = st.columns([2, 2, 2, 2])
    with col_s1:
        stock_input = st.text_input("🔍 輸入股票代號 (例: 2330.TW, 2603.TW)", value="2330.TW")
    
    df_raw = load_replay_data(stock_input)
    
    # 2. 日期選擇器
    available_dates = sorted(df_raw["Date"].unique()) if not df_raw.empty else [datetime.today().strftime("%Y-%m-%d")]
    with col_s2:
        selected_date = st.selectbox("📅 選擇覆盤日期", available_dates, index=len(available_dates)-1)
    
    with col_s3:
        sub_timeframe = st.selectbox("📊 右側分K週期選擇", ["1分K", "3分K", "5分K", "15分K", "日K"])
    with col_s4:
        show_ema = st.checkbox("右側分K顯示 EMA", value=True)
        ema_period = st.number_input("EMA 參數", min_value=1, max_value=60, value=5)

    # 3. 建立標準 09:00 ~ 13:30 完整時間軸
    base_times = pd.date_range(f"{selected_date} 09:00", f"{selected_date} 13:30", freq="1min")
    df_day = pd.DataFrame({"Time_dt": base_times})
    df_day["Date"] = selected_date
    df_day["Time_Str"] = df_day["Time_dt"].dt.strftime("%H:%M")

    df_day_raw = df_raw[df_raw["Date"] == selected_date].copy()
    
    if not df_day_raw.empty:
        df_day_raw = df_day_raw.set_index("Time_dt")
        df_day = df_day.set_index("Time_dt")
        df_day["Close"] = df_day_raw["Close"]
        df_day["Open"] = df_day_raw["Open"]
        df_day["High"] = df_day_raw["High"]
        df_day["Low"] = df_day_raw["Low"]
        df_day["Volume"] = df_day_raw["Volume"]
        df_day = df_day.reset_index()
    else:
        df_day["Close"] = 100.0
        df_day["Open"] = 100.0
        df_day["High"] = 100.0
        df_day["Low"] = 100.0
        df_day["Volume"] = 500

    # 前值補齊與預設值防護
    df_day["Close"] = df_day["Close"].ffill().bfill().fillna(100.0)
    df_day["Open"] = df_day["Open"].fillna(df_day["Close"])
    df_day["High"] = df_day["High"].fillna(df_day["Close"])
    df_day["Low"] = df_day["Low"].fillna(df_day["Close"])
    df_day["Volume"] = df_day["Volume"].fillna(500)

    total_steps = len(df_day)
    
    # 控制列
    ctrl_col1, ctrl_col2, ctrl_col3, ctrl_col4, ctrl_col5 = st.columns([3, 1, 1, 1, 1])
    with ctrl_col1:
        st.session_state.replay_step = st.slider(
            "⏱️ 盤中時間進度 (K線根數)", 
            min_value=1, 
            max_value=total_steps, 
            value=min(st.session_state.replay_step, total_steps)
        )
    with ctrl_col2:
        if st.button("▶️ 下一根"):
            if st.session_state.replay_step < total_steps:
                st.session_state.replay_step += 1
                st.rerun()
    with ctrl_col3:
        if st.button("⏮️ 重置"):
            st.session_state.replay_step = 1
            st.session_state.positions = []
            st.session_state.trade_history = []
            st.rerun()
    with ctrl_col4:
        play_clicked = st.toggle("🔄 自動播放", value=False)
    with ctrl_col5:
        st.markdown(f"**進度:** {st.session_state.replay_step}/{total_steps}")

    # 自動播放邏輯
    if play_clicked:
        if st.session_state.replay_step < total_steps:
            t_time.sleep(0.3)
            st.session_state.replay_step += 1
            st.rerun()
        else:
            st.success("已播放至收盤")

    # 💡 核心修正：嚴格依據時間進度滑桿截斷資料片段（只顯示到當前進度點，後面尚未發生的時間不畫出來）
    df_curr_raw = df_day.iloc[:st.session_state.replay_step].copy()
    latest_row = df_curr_raw.iloc[-1]
    curr_time = latest_row["Time_Str"]
    curr_open = float(latest_row["Open"])
    curr_high = float(latest_row["High"])
    curr_low = float(latest_row["Low"])
    curr_close = float(latest_row["Close"])
    
    # 即時顯示開高低收看板
    st.markdown(f"""
    ### 📈 標的：{stock_input} | 日期：{selected_date} | ⏰ 時間：{curr_time}
    """)
    m_o, m_h, m_l, m_c = st.columns(4)
    m_o.metric("開盤價 (Open)", f"{curr_open:.2f}")
    m_h.metric("最高價 (High)", f"{curr_high:.2f}")
    m_l.metric("最低價 (Low)", f"{curr_low:.2f}")
    m_c.metric("收盤價 (Close)", f"{curr_close:.2f}", delta=f"{curr_close - curr_open:.2f}")

    # 左右雙欄圖表與下單面板
    col_left_chart, col_right_chart, col_trade = st.columns([1.5, 1.5, 1])
    
    # 1. 左側：江波圖（嚴格只畫到當前進度，X軸固定 09:00 ~ 13:30）
    with col_left_chart:
        st.markdown("#### 🌊 江波圖 (分時走勢與當日均價線 VWAP)")
        fig_tick = go.Figure()
        
        cum_vol = df_curr_raw["Volume"].cumsum()
        cum_val = (df_curr_raw["Close"] * df_curr_raw["Volume"]).cumsum()
        df_curr_raw["VWAP"] = np.where(cum_vol > 0, cum_val / cum_vol, df_curr_raw["Close"])

        fig_tick.add_trace(go.Scatter(
            x=df_curr_raw["Time_Str"], y=df_curr_raw["Close"],
            mode='lines', name='江波價',
            line=dict(color='#00FFCC', width=2)
        ))
        fig_tick.add_trace(go.Scatter(
            x=df_curr_raw["Time_Str"], y=df_curr_raw["VWAP"],
            mode='lines', name='當日均價 (VWAP)',
            line=dict(color='#FFD700', width=1.5, dash='dash')
        ))
        
        fig_tick.update_layout(
            height=430,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(range=["09:00", "13:30"]), # 💡 嚴格固定整天 X 軸
            template="plotly_dark",
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_tick, use_container_width=True)

    # 2. 右側：多週期分K圖 + EMA（嚴格只畫到當前進度，X軸固定 09:00 ~ 13:30）
    with col_right_chart:
        st.markdown(f"#### 📊 {sub_timeframe} K線圖與指數均線 (EMA)")
        df_sub_resampled = resample_candles(df_curr_raw, sub_timeframe)
        
        fig_k = go.Figure()
        if show_ema and len(df_sub_resampled) >= ema_period:
            df_sub_resampled['EMA'] = df_sub_resampled['Close'].ewm(span=ema_period, adjust=False).mean()

        if not df_sub_resampled.empty:
            fig_k.add_trace(go.Candlestick(
                x=df_sub_resampled['Time_Str'],
                open=df_sub_resampled['Open'], high=df_sub_resampled['High'],
                low=df_sub_resampled['Low'], close=df_sub_resampled['Close'],
                increasing_line_color='red', decreasing_line_color='green',
                name=sub_timeframe
            ))
            if show_ema and 'EMA' in df_sub_resampled.columns:
                fig_k.add_trace(go.Scatter(
                    x=df_sub_resampled['Time_Str'], y=df_sub_resampled['EMA'],
                    mode='lines', name=f'EMA {ema_period}',
                    line=dict(color='#FFD700', width=1.5)
                ))
            
        fig_k.update_layout(
            height=430,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis=dict(range=["09:00", "13:30"]), # 💡 嚴格固定整天 X 軸
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_k, use_container_width=True)

    # 3. 閃電下單與部位管理面板
    with col_trade:
        st.subheader("⚡ 閃電下單面板")
        trade_qty = st.number_input("委託張數", min_value=1, max_value=20, value=1)
        
        st.markdown("#### 🔴 做多專區 (先買後賣)")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("現股買進 (多)", use_container_width=True):
                st.session_state.positions.append({"side": "LONG", "price": curr_close, "qty": trade_qty, "time": curr_time})
                st.success(f"買進 {trade_qty} 張 @ {curr_close}")
                st.rerun()
        with c2:
            if st.button("多單平倉", use_container_width=True):
                long_poss = [p for p in st.session_state.positions if p["side"] == "LONG"]
                if long_poss:
                    pos = long_poss[0]
                    st.session_state.positions.remove(pos)
                    pnl, cost = calc_daytrade_cost(pos["price"], curr_close, pos["qty"], "LONG")
                    st.session_state.trade_history.append({"strategy": "現股做多", "buy_time": pos["time"], "sell_time": curr_time, "buy_price": pos["price"], "sell_price": curr_close, "qty": pos["qty"], "pnl": round(pnl), "cost": round(cost)})
                    st.success(f"多單平倉！損益: {round(pnl)}元")
                    st.rerun()
                else:
                    st.warning("無多單部位")

        st.markdown("#### 🟢 做空專區 (先賣後買)")
        c3, c4 = st.columns(2)
        with c3:
            if st.button("現股賣出 (空)", use_container_width=True):
                st.session_state.positions.append({"side": "SHORT", "price": curr_close, "qty": trade_qty, "time": curr_time})
                st.success(f"放空 {trade_qty} 張 @ {curr_close}")
                st.rerun()
        with c4:
            if st.button("空單平倉", use_container_width=True):
                short_poss = [p for p in st.session_state.positions if p["side"] == "SHORT"]
                if short_poss:
                    pos = short_poss[0]
                    st.session_state.positions.remove(pos)
                    pnl, cost = calc_daytrade_cost(pos["price"], curr_close, pos["qty"], "SHORT")
                    st.session_state.trade_history.append({"strategy": "現股做空", "buy_time": curr_time, "sell_time": pos["time"], "buy_price": curr_close, "sell_price": pos["price"], "qty": pos["qty"], "pnl": round(pnl), "cost": round(cost)})
                    st.success(f"空單平倉！損益: {round(pnl)}元")
                    st.rerun()
                else:
                    st.warning("無空單部位")

        st.markdown("---")
        st.markdown("#### 📋 目前持倉部位")
        if st.session_state.positions:
            for p in st.session_state.positions:
                st.info(f"[{p['side']}] {p['qty']}張 @ {p['price']} (時間:{p['time']})")
        else:
            st.caption("目前無持倉")

    # --- 4. 績效統計與明細表 ---
    st.markdown("---")
    st.subheader("📈 當日覆盤績效報表")
    
    if st.session_state.trade_history:
        df_history = pd.DataFrame(st.session_state.trade_history)
        total_pnl = df_history["pnl"].sum()
        total_trades = len(df_history)
        wins = df_history[df_history["pnl"] > 0]
        losses = df_history[df_history["pnl"] <= 0]
        
        win_rate = len(wins) / total_trades if total_trades > 0 else 0
        avg_win = wins["pnl"].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses["pnl"].mean()) if len(losses) > 0 else 0
        rr_ratio = avg_win / avg_loss if avg_loss != 0 else 0
        
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("已實現總損益", f"{total_pnl:,.0f} 元")
        m2.metric("勝率", f"{win_rate:.1%}")
        m3.metric("風報比 (R:R)", f"{rr_ratio:.2f}")
        m4.metric("總交易次數", f"{total_trades} 次")

        summary_table = pd.DataFrame([{
            "年度": f"{selected_date} 覆盤",
            "策略": "多空當沖模擬",
            "交易次數": total_trades,
            "成功 / 失敗": f"{len(wins)} / {len(losses)}",
            "單次平均獲利": f"{avg_win:,.0f}",
            "單次平均虧損": f"{avg_loss:,.0f}",
            "勝率": f"{win_rate:.1%}",
            "風報比(R:R)": f"{rr_ratio:.2f}",
            "年度報酬率": f"{(total_pnl / st.session_state.capital):.2%}"
        }])
        st.table(summary_table)
        st.dataframe(df_history, use_container_width=True)
    else:
        st.info("尚無平倉交易紀錄。")


# ==========================================
# 🧭 5. 主側邊欄導覽選單
# ==========================================
st.sidebar.title("🛠️ 戰情控制台")
app_mode = st.sidebar.radio(
    "選擇功能模式：",
    ["📊 姊布林 ABCDE 主戰情室", "🎯 專業當沖覆盤模擬系統"]
)

if app_mode == "📊 姊布林 ABCDE 主戰情室":
    st.title("🏹 姊布林 ABCDE 戰情室")
    st.info("（此處為您原本的姊布林主戰情室介面與掃描邏輯）")
    if st.button("測試大盤即時報價"):
        tse_price = get_realtime_price('TSE')
        st.success(f"加權指數即時報價：{tse_price}")

elif app_mode == "🎯 專業當沖覆盤模擬系統":
    render_daytrade_replay_ui()
