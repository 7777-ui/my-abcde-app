# --- 修正後的營收動能處理塊 ---
elif mode == "營收動能策略":
    st.sidebar.info("💡 系統將讀取 revenue_data/ 內近三月 CSV。")
    if st.sidebar.button("📊 啟動營收動能分析"):
        folder = "revenue_data"
        # 確保檔案路徑正確且排序
        all_files = sorted(glob.glob(os.path.join(folder, "*.csv")), reverse=True)
        
        if len(all_files) < 3:
            st.warning("⚠️ CSV 檔案不足三個月，請檢查 revenue_data 資料夾。")
        else:
            recent_files = all_files[:3]
            month_dfs = []
            
            with st.spinner("🔍 正在進行深度資料清洗與對齊..."):
                for f in recent_files:
                    try:
                        # 自動偵測編碼並讀取
                        try: t_df = pd.read_csv(f, encoding='utf-8-sig')
                        except: t_df = pd.read_csv(f, encoding='cp950')
                        
                        # 清洗欄位名稱與內容
                        t_df.columns = [c.strip() for c in t_df.columns]
                        t_df['公司代號'] = t_df['公司代號'].astype(str).str.strip()
                        
                        # 處理營收數值：移除逗號並轉為數值
                        target_col = '營業收入-當月營收'
                        if target_col in t_df.columns:
                            t_df[target_col] = pd.to_numeric(t_df[target_col].astype(str).str.replace(',', ''), errors='coerce')
                            month_dfs.append(t_df[['公司代號', '公司名稱', target_col]])
                    except Exception as e:
                        st.error(f"檔案 {f} 讀取失敗: {e}")

                # 開始合併與計算
                if len(month_dfs) == 3:
                    m1, m2, m3 = month_dfs[0], month_dfs[1], month_dfs[2]
                    
                    # 使用左連接確保以最近一個月為準，並過濾重複項
                    m1 = m1.drop_duplicates(subset=['公司代號'])
                    merged = m1.rename(columns={'營業收入-當月營收': 'rev1'})
                    merged = merged.merge(m2[['公司代號', '營業收入-當月營收']].rename(columns={'營業收入-當月營收': 'rev2'}), on='公司代號', how='inner')
                    merged = merged.merge(m3[['公司代號', '營業收入-當月營收']].rename(columns={'營業收入-當月營收': 'rev3'}), on='公司代號', how='inner')
                    
                    # 計算增長率 (LaTeX 邏輯應用)
                    # g = (當月 - 前月) / 前月
                    merged['g1'] = (merged['rev1'] - merged['rev2']) / merged['rev2']
                    merged['g2'] = (merged['rev2'] - merged['rev3']) / merged['rev3']
                    merged['avg_growth'] = (merged['g1'] + merged['g2']) / 2 * 100
                    
                    # 篩選平均增長率 > 20%
                    targets = merged[merged['avg_growth'] > 20].copy()
                    
                    if targets.empty:
                        st.info("查無符合平均增長 > 20% 的標的。")
                    else:
                        # 進行後續行情掃描 (同前段 logic)
                        # ... (這裡接續原本的行情處理流程)
                        st.success(f"找到 {len(targets)} 檔符合營收動能標的")
                        st.session_state.scan_results = targets # 暫存結果
