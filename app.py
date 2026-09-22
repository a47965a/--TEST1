import streamlit as st
import pandas as pd
import json
import io
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="發票與 Packing List 自動解析工具", layout="wide")

st.title("📄 發票與 Packing List 自動解析工具")
st.caption("上傳 PDF 或圖片檔，自動解析明細並將 INVOICE 與 PACKING LIST 分頁匯出至 Excel。")

# 讀取 Secrets 中的 API Key
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader("選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件，並依 INVOICE 與 PACKING 分頁處理中..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type

                prompt = """
                請解析這份半導體/電子零件文件，將 INVOICE 與 PACKING LIST 的明細資料分開擷取，並回傳格式嚴格為包含兩個 key 的 JSON Object：
                {
                  "invoice_data": [ ... ],
                  "packing_data": [ ... ]
                }

                1. "invoice_data"（發票明細陣列），每筆資料必須包含以下欄位：
                   - "頁碼"
                   - "發票號碼"
                   - "型號"
                   - "封裝規格"
                   - "PO單號"
                   - "項次"
                   - "數量"
                   - "單價"
                   - "總價"
                   - "發票總金額" (僅在該張 Invoice 的最後一筆明細顯示總額，其餘為空字串 "")

                2. "packing_data"（裝箱單明細陣列），每筆資料必須包含以下欄位：
                   - "頁碼"
                   - "LIST NO/單號" (填寫 Packing List No. 或 Packing No.)
                   - "型號"
                   - "封裝規格"
                   - "PO單號"
                   - "項次"
                   - "數量"
                   - "總 GW (KGS)" (僅在該張 Packing List 的最後一筆明細顯示，其餘為空字串 "")
                   - "總 NW (KGS)" (僅在該張 Packing List 的最後一筆明細顯示，其餘為空字串 "")

                注意事項：
                - 每個品項都要拆成獨立的一行（No merged rows）。
                - 請勿混淆 Invoice 與 Packing List 的數據。
                - 回傳格式請嚴格遵守純 JSON Object 格式，不要包含 Markdown 標記（如 ```json ）。
                """

                # 動態獲取該 API Key 支援的模型
                available_models = []
                try:
                    for m in client.models.list():
                        if hasattr(m, 'supported_generation_methods') and 'generateContent' in m.supported_generation_methods:
                            name = m.name.replace('models/', '')
                            available_models.append(name)
                        elif not hasattr(m, 'supported_generation_methods'):
                            name = m.name.replace('models/', '')
                            available_models.append(name)
                except Exception:
                    available_models = ["gemini-2.5-flash", "gemini-2.0-flash"]

                flash_models = [m for m in available_models if 'flash' in m.lower()]
                other_models = [m for m in available_models if 'flash' not in m.lower()]
                models_to_try = flash_models + other_models

                if not models_to_try:
                    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]

                response = None
                last_error = None

                for model_name in models_to_try:
                    for attempt in range(2):
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=[
                                    types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                                    prompt,
                                ],
                            )
                            if response and response.text:
                                break
                        except Exception as e:
                            last_error = e
                            err_msg = str(e)
                            if "503" in err_msg or "UNAVAILABLE" in err_msg or "429" in err_msg:
                                time.sleep(2)
                                continue
                            else:
                                break
                    if response and response.text:
                        break

                if not response or not response.text:
                    raise last_error

                clean_json = (
                    response.text.replace("```json", "").replace("```", "").strip()
                )
                raw_data = json.loads(clean_json)

                # 轉為 DataFrame
                df_inv = pd.DataFrame(raw_data.get("invoice_data", []))
                df_pack = pd.DataFrame(raw_data.get("packing_data", []))

                # 確保 Invoice 欄位與順序
                inv_cols = ["頁碼", "發票號碼", "型號", "封裝規格", "PO單號", "項次", "數量", "單價", "總價", "發票總金額"]
                for col in inv_cols:
                    if col not in df_inv.columns:
                        df_inv[col] = ""
                df_inv = df_inv[inv_cols]

                # 確保 Packing 欄位與順序
                pack_cols = ["頁碼", "LIST NO/單號", "型號", "封裝規格", "PO單號", "項次", "數量", "總 GW (KGS)", "總 NW (KGS)"]
                for col in pack_cols:
                    if col not in df_pack.columns:
                        df_pack[col] = ""
                df_pack = df_pack[pack_cols]

                # 畫面上預覽兩張表
                st.subheader("🧾 Invoice（發票）解析結果預覽")
                st.dataframe(df_inv, use_container_width=True)

                st.subheader("📦 Packing List（裝箱單）解析結果預覽")
                st.dataframe(df_pack, use_container_width=True)

                # 寫入包含 2 個 Sheet 的 Excel 檔案
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df_inv.to_excel(writer, index=False, sheet_name="Invoice")
                    df_pack.to_excel(writer, index=False, sheet_name="Packing_List")
                excel_data = output.getvalue()

                st.download_button(
                    label="📥 下載多頁籤 Excel 檔案 (.xlsx)",
                    data=excel_data,
                    file_name=f"Parsed_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success("解析成功！Excel 已自動分開為 [Invoice] 與 [Packing_List] 兩個工作表。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
