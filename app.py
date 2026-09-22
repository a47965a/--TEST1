import json
import pandas as pd
import streamlit as st
from google import genai
from google.genai import types

st.set_page_config(
    page_title="半導體發票解析工具", page_icon="📄", layout="wide"
)

st.title("📄 發票與 Packing List 自動解析工具")
st.write("上傳 PDF 或圖片檔，自動解析明細並導出 Excel。")

api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
  api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

uploaded_file = st.file_uploader(
    "選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file and api_key:
  if st.button("🚀 開始解析"):
    with st.spinner("AI 正在辨識並比對資料，請稍候..."):
      try:
        client = genai.Client(api_key=api_key)
        file_bytes = uploaded_file.read()
        mime_type = uploaded_file.type

        prompt = """
                  請解析這份發票/Packing List，將欄位抽取並以 JSON Array 格式回傳。
                  包含欄位：頁碼, 發票號碼, 型號, 封裝規格, PO單號, 項次, 數量, 單價, 總價, 發票總金額
                  規則：
                  1. 每個品項都要列出成獨立的一行 (No merged rows)。
                  2. 「發票總金額」只顯示在該張發票最後一個項次那一列，其餘列設為 null 或空字串。
                  3. 回傳格式請嚴格遵守純 JSON Array 格式，不要包含 Markdown 標記。
                  """

        response = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
                prompt,
            ],
        )

        clean_json = (
            response.text.replace("```json", "").replace("```", "").strip()
        )
        data = json.loads(clean_json)
        df = pd.DataFrame(data)

        st.subheader("📊 解析結果預覽")
        st.dataframe(df, use_container_width=True)

        import io

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
          df.to_excel(writer, index=False, sheet_name="Invoice_Data")

        st.download_button(
            label="📥 下載成 Excel 檔案 (.xlsx)",
            data=output.getvalue(),
            file_name="Invoice_Parsed_Result.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ),
        )
      except Exception as e:
        st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
elif uploaded_file and not api_key:
  st.warning("請先於左側輸入 Gemini API Key 以繼續使用。")
