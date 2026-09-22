import streamlit as st
import pandas as pd
import json
import io
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="發票與 Packing List 自動解析工具", layout="wide")

st.title("📄 發票與 Packing List 自動解析工具")
st.caption("上傳 PDF 或圖片檔，自動解析明細，區分 INVOICE 與 PACKING LIST 並導出 13 欄標準 Excel 格式。")

# 讀取 Secrets 中的 API Key
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader("選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件細節、區分單據類型中，請稍候..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type

                prompt = """
                請解析這份半導體/電子零件發票或 Packing List，將每個品項明細抽取出來，並嚴格以 JSON Array 格式回傳。
                
                必須精準包含以下 13 個欄位（欄位名稱請完全一致）：
                1. "單據類型"
                2. "頁碼"
                3. "發票號碼/單號"
                4. "型號"
                5. "封裝規格"
                6. "PO單號"
                7. "項次"
                8. "數量"
                9. "單價"
                10. "總價"
                11. "發票總金額"
                12. "總 GW (KGS)"
                13. "總 NW (KGS)"

                解析與分類規則（極重要）：
                1. 「單據類型」請填寫 "INVOICE" 或 "PACKING LIST"。
                2. 「發票號碼/單號」：
                   - 若為 INVOICE，填寫 Invoice No.（例：1S555-260800073）。
                   - 若為 PACKING LIST，填寫 LIST NO 或 PACKING NO（例：PACKING-26820664 或 LIST NO: 26820664）。
                3. 若該列為 INVOICE：
                   - 請解析單價、總價，並在最後一列填寫「發票總金額」。
                   - 「總 GW (KGS)」與「總 NW (KGS)」請填寫空字串 ""。
                4. 若該列為 PACKING LIST：
                   - 「單價」、「總價」、「發票總金額」請填寫空字串 ""。
                   - 請從該 Packing List 頁尾或總計處提取「總 GW (KGS)」與「總 NW (KGS)」，並僅顯示在該張 Packing List 的最後一個項次那一列。
                5. 每個品項都要拆成獨立的一行（No merged rows）。
                6. 回傳格式請嚴格遵守純 JSON Array 格式，不要包含 Markdown 標記（如 ```json ）。
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

                # 固定 13 欄順序
                expected_cols = [
                    "單據類型", "頁碼", "發票號碼/單號", "型號", "封裝規格", "PO單號", 
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
                    df.to_excel(writer, index=False, sheet_name="Parsed_Data")
                excel_data = output.getvalue()

                st.download_button(
                    label="📥 下載成 Excel 檔案 (.xlsx)",
                    data=excel_data,
                    file_name=f"Parsed_{uploaded_file.name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
                st.success("解析成功！已成功分開 INVOICE 與 PACKING LIST 資料。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
