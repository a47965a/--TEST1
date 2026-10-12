import json
import os
import time
from datetime import datetime
from google import genai
from google.genai import types
import streamlit as st

# 從 parsers 資料夾匯入模組
from parsers.benq_parser import process_benq_compare
from parsers.upi_parser import process_upi_semiconductor

# 1. 頁面基本設定
st.set_page_config(
    page_title="Shipping Docs 自動解析工具",
    layout="wide",
)

st.title("📄 Shipping Docs 自動解析工具")
st.caption("支援供應商: 力智、明基(報單轉換)")
st.info("💡 提示：若 AI 解析超過 3 分鐘仍未完成，請重新整理網頁並重新上傳檔案進行嘗試。")

# 歷史紀錄實體檔案路徑
HISTORY_FILE = "history.json"


def load_history():
    """從伺服器硬碟讀取歷史紀錄"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history_list):
    """將歷史紀錄寫入伺服器硬碟"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history_list, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"儲存歷史紀錄失敗: {e}")


# 初始化全站共用的歷史紀錄清單 (從檔案讀取)
if "global_history" not in st.session_state:
    st.session_state.global_history = load_history()

# =========================================================
# 📂 側邊欄專區：API Key 與 🔒 受密碼保護的管理者紀錄檢視
# =========================================================
# 讀取 Secrets 中的 API Key，若無則從 Sidebar 輸入
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    api_key = st.sidebar.text_input("輸入 Gemini API Key", type="password")

st.sidebar.markdown("---")
st.sidebar.subheader("👑 管理者專區")

# 輸入密碼才能解鎖查看紀錄
admin_pwd_input = st.sidebar.text_input("管理者解鎖密碼", type="password")
# 從 Secrets 讀取設定的密碼，若無則預設為 "admin123"
correct_admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")

# 只有密碼正確時才顯示上傳紀錄清單
if admin_pwd_input == correct_admin_pwd and admin_pwd_input != "":
    st.sidebar.success("✅ 管理者已解鎖")
    st.sidebar.markdown("### 📊 使用者上傳紀錄")

    if st.session_state.global_history:
        if st.sidebar.button("🗑️ 清空所有紀錄"):
            st.session_state.global_history = []
            if os.path.exists(HISTORY_FILE):
                os.remove(HISTORY_FILE)
            st.rerun()

        st.sidebar.markdown("---")
        for item in st.session_state.global_history:
            st.sidebar.text(
                f"🕒 {item['time']}\n📁 {item['filename']}\n🏷️ {item['doc_type']}"
            )
            st.sidebar.markdown("---")
    else:
        st.sidebar.info("目前尚無任何上傳解析紀錄。")
else:
    if admin_pwd_input != "":
        st.sidebar.error("❌ 密碼錯誤")
    st.sidebar.caption("（一般訪客請忽略此區塊）")

# =========================================================
# 🚀 主畫面：檔案上傳與解析
# =========================================================
uploaded_file = st.file_uploader(
    "選擇 PDF 或圖片檔案", type=["pdf", "png", "jpg", "jpeg"]
)

if uploaded_file and api_key:
    if st.button("🚀 開始解析", type="primary"):
        with st.spinner("AI 正在深度解析文件，並自動辨識格式處理中..."):
            try:
                client = genai.Client(api_key=api_key)
                file_bytes = uploaded_file.read()
                mime_type = uploaded_file.type
                upload_time_str = datetime.now().strftime("%Y/%m/%d %H:%M:%S")

                prompt = (
                    "你是一個專業的半導體與電子零件 Shipping Docs 解析專家。"
                    "請閱讀這份文件，判斷文件屬於哪種格式 (document_type)：\n\n"
                    "【格式 A：BENQ_COMPARE】\n"
                    "若為 BENQ (明基材料) 的 Commercial Invoice 或海關出口報單 (含有 CW 報單號碼、GOODS NO、或 C5790 監管編號)：\n"
                    "1. 跨頁拼接與 BOM No 對齊：當報單跨頁時，請務必將第1頁最底部項次與第2頁頂部的續文完美拼接在一起。\n"
                    "2. 欄位純淨擷取：Item No 提取 S/N 後方料號，Item Description 提取完整品名規格與產地。\n\n"
                    "請回傳純 JSON Object 格式，包含 document_type 與 compare_data 或 invoice_data/packing_data。\n"
                    "注意事項：數量、單價、總價等數值欄位請回傳純數字 (不要加千分位逗號)。"
                )

                # 使用最新自動對應的 Flash 穩定模型代稱
                response = client.models.generate_content(
                    model="gemini-flash-latest",
                    contents=[
                        types.Part.from_bytes(
                            data=file_bytes, mime_type=mime_type
                        ),
                        prompt,
                    ],
                )

                if not response or not response.text:
                    raise Exception("AI 未能回傳有效結果，請重新嘗試。")

                clean_json = (
                    response.text.replace("```json", "")
                    .replace("```", "")
                    .strip()
                )
                raw_data = json.loads(clean_json)
                doc_type = raw_data.get("document_type", "UPI_SEMICONDUCTOR")

                # =========================================================
                # 處理轉換結果
                # =========================================================
                if doc_type == "BENQ_COMPARE":
                    df_compare, excel_bytes = process_benq_compare(raw_data)
                    file_name_out = "報單比對.xlsx"
                    preview_df = df_compare
                    st.success("✅ 自動辨識為 **BENQ/報單比對** 格式！")
                else:
                    df_inv, df_pack, excel_bytes = process_upi_semiconductor(
                        raw_data
                    )
                    file_name_out = f"Parsed_{uploaded_file.name}.xlsx"
                    preview_df = df_inv
                    st.success("✅ 自動辨識為 **力智/半導體** 格式！")

                # 顯示當次解析預覽與下載按鈕
                st.subheader("📋 解析結果預覽")
                st.dataframe(preview_df, use_container_width=True)

                st.download_button(
                    label=f"📥 下載產出的 Excel 檔案 ({file_name_out})",
                    data=excel_bytes,
                    file_name=file_name_out,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )

                # 將本筆紀錄推入清單並寫入 `history.json`
                new_record = {
                    "time": upload_time_str,
                    "filename": uploaded_file.name,
                    "doc_type": (
                        "BENQ 報單比對"
                        if doc_type == "BENQ_COMPARE"
                        else "力智半導體"
                    ),
                }
                st.session_state.global_history.insert(0, new_record)
                save_history(st.session_state.global_history)

                st.success("解析成功！")

            except Exception as e:
                st.error(f"解析失敗，請確認 API Key 或檔案格式是否正確：{e}")
