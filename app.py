import streamlit as st
import pandas as pd
import json
import io
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="發票與 Packing List 自動解析工具", layout="wide")

st.title("📄 發票與 Packing List 自動解析工具")
st.caption("上傳 PDF 或圖片檔，自動解析明細與總重，並導出 12 欄標準 Excel 格式。")

# 讀取 Secrets 中的 API Key
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader("選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件細節與重量資料中，請稍候..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type

                prompt = """
                請解析這份半導體/電子零件發票或 Packing List，將每個品項明細抽取出來，並嚴格以 JSON Array 格式回傳。
                
                必須精準包含以下 12 個欄位（欄位名稱請完全一致）：
                1. "頁碼"
                2. "發票號碼"
                3. "型號"
                4. "封裝規格"
                5. "PO單號"
                6. "項次"
                7. "數量"
                8. "單價"
                9. "總價"
                10. "發票總金額"
                11. "總 GW (KGS)"
                12. "總 NW (KGS)"

                解析規則：
                1. 每個品項都要拆成獨立的一行（No merged rows）。
                2. 「發票總金額」、「總 GW (KGS)」、「總 NW (KGS)」為全域統計數值，請從文件頁尾或總計處提取。
                3. 「發票總金額」、「總 GW (KGS)」、「總 NW (KGS)」只顯示在該張文件最後一個項次那一列，其餘明細列設為 null 或空字串（避免重複加總）。如果文件沒有提及重量，則填寫空字串。
                4. 數量、單價、總價、重量等數值欄位請保留純數字或標準數字格式（例：12.50）。
                5. 回傳格式請嚴格遵守純 JSON Array 格式，不要包含 Markdown 標記（如 ```json ）。
                """

                # 動態獲取該 API Key 支援的所有可產生內容的模型
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

                # 優先排序：Flash 系列優先
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
                data = json.loads(clean_json)
                df = pd.DataFrame(data)

                # 固定 12 欄順序
                expected_cols = [
                    "頁碼", "發票號碼", "型號", "封裝規格", "PO單號", 
                    "項次", "數量", "單價", "總價", "發票總金額",
                    "總 GW (KGS)", "總 NW (KGS)"
                ]
                for col in expected_cols:
                    if col not in df.columns:
                        df[col] = ""
                df = df[expected_cols]

                st.subheader("📊 解析結果預覽")
                st.dataframe(df, use_container_width=True)

                # 匯出為 Excel 檔案
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine="openpyxl") as writer:
                    df.to_excel(writer, index=False, sheet_name="Packing_List_Parsed")
                excel_data = output.getvalue()

                st.download_button(
                    label="📥 下載成 Excel 檔案 (.xlsx)",
                    data=excel_data,
                    file_name=f"Parsed_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success("解析成功！已包含 12 欄明細與重量數據。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
