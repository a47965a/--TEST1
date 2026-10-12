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

                # 動態搜尋與嘗試模型
                available_models = []
                try:
                    for m in client.models.list():
                        m_name = (
                            m.name.replace("models/", "")
                            if hasattr(m, "name")
                            else str(m)
                        )
                        if (
                            hasattr(m, "supported_generation_methods")
                            and "generateContent"
                            in m.supported_generation_methods
                        ):
                            available_models.append(m_name)
                        elif not hasattr(m, "supported_generation_methods"):
                            available_models.append(m_name)
                except Exception:
                    available_models = [
                        "gemini-2.5-flash",
                        "gemini-2.0-flash",
                        "gemini-1.5-flash",
                    ]

                flash_models = [
                    m for m in available_models if "flash" in m.lower()
                ]
                other_models = [
                    m for m in available_models if "flash" not in m.lower()
                ]
                models_to_try = flash_models + other_models

                if not models_to_try:
                    models_to_try = [
                        "gemini-2.5-flash",
                        "gemini-2.0-flash",
                        "gemini-1.5-flash",
                    ]

                response = None
                last_error = None

                for model_name in models_to_try:
                    for attempt in range(2):
                        try:
                            response = client.models.generate_content(
                                model=model_name,
                                contents=[
                                    types.Part.from_bytes(
                                        data=file_bytes, mime_type=mime_type
                                    ),
                                    prompt,
                                ],
                            )
                            if response and response.text:
                                break
                        except Exception as e:
                            last_error = e
                            err_msg = str(e)
                            if (
                                "503" in err_msg
                                or "UNAVAILABLE" in err_msg
                                or "429" in err_msg
                            ):
                                time.sleep(2)
                                continue
                            else:
                                break
                    if response and response.text:
                        break

                if not
