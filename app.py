import streamlit as st
import pandas as pd
import json
import io
import time
from google import genai
from google.genai import types

st.set_page_config(page_title="發票與 Packing List 自動解析工具", layout="wide")

st.title("📄 發票與 Packing List 自動解析工具")
st.caption("上傳 PDF 或圖片檔，自動解析明細並導出 10 欄標準 Excel 格式。")

# 讀取 Secrets 中的 API Key
api_key = st.secrets.get("GEMINI_API_KEY", "")

if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader("選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"])

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件細節中，請稍候..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type

                prompt = """
                請解析這份半導體/電子零件發票或 Packing List，將每個品項明細抽取出來，並嚴格以 JSON Array 格式回傳。
                
                必須精準包含以下 10 個欄位（欄位名稱請完全一致）：
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

                解析規則：
                1. 每個品項都要拆成獨立的一行（No merged rows）。
                2. 「發票總金額」只顯示在該張發票最後一個項次那一列，其餘列設為 null 或空字串。
                3. 數量、單價、總價等數值欄位請保留純數字或標準格式。
                4. 回傳格式請嚴格遵守純 JSON Array 格式，不要包含 Markdown 標記（如 ```json ）。
                """

                # 動態獲取該 API Key 支援的所有可產生內容的模型
                available_models = []
                try:
                    for m in client.models.list():
                        # 過濾出支援 generateContent 的模型名稱
                        if hasattr(m, 'supported_generation_methods') and 'generateContent' in m.supported_generation_methods:
                            name = m.name.replace('models/', '')
                            available_models.append(name)
                        elif not hasattr(m, 'supported_generation_methods'):
                            name = m.name.replace('models/', '')
                            available_models.append(name)
                except Exception:
                    # 若無法動態取得，則提供最主流安全的預設名稱
                    available_models = ["gemini-2.5-flash", "gemini-2.0-flash"]

                # 優先排序：Flash 系列優先（速度快且限制較鬆），再來是其他模型
                flash_models = [m for m in available_models if 'flash' in m.lower()]
                other_models = [m for m in available_models if 'flash' not in m.lower()]
                models_to_try = flash_models + other_models

                if not models_to_try:
                    models_to_try = ["gemini-2.5-flash", "gemini-2.0-flash"]

                response = None
                last_error = None

                for model_name in models_to_try:
                    for attempt in range(2):  # 每個模型嘗試最多 2 次
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
                                time.sleep(2)  # 503/429 忙碌限流時等待 2 秒再重試
                                continue
                            else:
                                break  # 其他錯誤（如 404）跳過直接試下一個模型
                    if response and response.text:
                        break  # 成功取得解析結果，跳出模型嘗試迴圈

                if not response or not response.text:
                    raise last_error

                clean_json = (
                    response.text.replace("```json", "").replace("```", "").strip()
                )
                data = json.loads(clean_json)
                df = pd.DataFrame(data)

                # 固定 10 欄順序
                expected_cols = [
                    "頁碼", "發票號碼", "型號", "封裝規格", "PO單號", 
                    "項次", "數量", "單價", "總價", "發票總金額"
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
                st.success("解析成功！請點擊上方按鈕下載 Excel。")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
