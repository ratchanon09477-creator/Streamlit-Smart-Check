import streamlit as st
from inference_sdk import InferenceHTTPClient
from PIL import Image, ImageDraw
import os
from datetime import datetime
from streamlit_javascript import st_javascript
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import tempfile

# 1. ตั้งค่าหน้าตา UI ให้เรียบร้อย
st.set_page_config(page_title="Smart Check App - Cloud Version", page_icon="🚪", layout="wide")

st.markdown("""
    <style>
    .status-pass {
        background-color: #D4EDDA; color: #155724; padding: 20px;
        border-radius: 12px; text-align: center; font-size: 24px; font-weight: bold;
        margin-bottom: 20px; border: 3px solid #C3E6CB;
    }
    .status-fail {
        background-color: #F8D7DA; color: #721C24; padding: 20px;
        border-radius: 12px; text-align: center; font-size: 24px; font-weight: bold;
        margin-bottom: 20px; border: 3px solid #F5C6CB;
    }
    .item-box {
        padding: 14px; border-radius: 10px; margin-bottom: 10px; font-size: 18px; font-weight: bold;
    }
    div[data-testid="stCameraInput"] {
        max-width: 100% !important;
        margin: 0 auto;
    }
    .admin-card-present {
        color: #28a745; font-weight: bold; font-size: 14px; margin: 2px 0;
    }
    .admin-card-missing {
        color: #dc3545; font-weight: bold; font-size: 14px; margin: 2px 0;
    }
    </style>
""", unsafe_allow_html=True)

# ☁️ ฟังก์ชันเชื่อมต่อและอัปโหลดไฟล์ขึ้น Google Drive
def upload_file_to_drive(local_file_path, file_name, mime_type="image/jpeg"):
    try:
        # ดึงค่า Secrets จาก Streamlit
        gdrive_creds = dict(st.secrets["google_service_account"])
        folder_id = st.secrets["GDRIVE_FOLDER_ID"]
        
        credentials = service_account.Credentials.from_service_account_info(
            gdrive_creds, scopes=['https://www.googleapis.com/auth/drive']
        )
        service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': file_name,
            'parents': [folder_id]
        }
        media = MediaFileUpload(local_file_path, mimetype=mime_type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return True
    except Exception as e:
        st.error(f"อัปโหลดไป Google Drive ไม่สำเร็จ: {e}")
        return False

# 2. ฟังก์ชันโหลดโมเดล AI
@st.cache_resource
def load_model():
    api_key = "xWM1igmZO9XPzWUoOmBc"
    project_id = "detect-object-dfq6s"
    version_id = 15
    client = InferenceHTTPClient(api_url="https://detect.roboflow.com", api_key=api_key)
    return client, f"{project_id}/{version_id}"

try:
    client, model_id = load_model()
except Exception as e:
    st.error("ไม่สามารถเชื่อมต่อโมเดลได้")

REQUIRED_CLASSES = ["wallet", "phone", "key"]
CLASS_MAPPING_TH = {
    "wallet": "💳 กระเป๋าสตางค์ (Wallet)",
    "phone": "📱 โทรศัพท์มือถือ (Phone)",
    "key": "🔑 กุญแจ (Key)"
}

# ==========================================
# 🗺️ เมนูแถบด้านข้าง (Sidebar Navigation)
# ==========================================
st.sidebar.title("📌 เมนูควบคุมระบบ")
app_mode = st.sidebar.selectbox("เลือกหน้าเว็บที่ต้องการเข้าชม:", ["📸 หน้าหลัก (ตรวจเช็คสิ่งของ)", "📊 ข้อมูลระบบคลาวด์"])

# ------------------------------------------
# โหมดที่ 1: หน้าหลักตรวจเช็คสิ่งของ (User Mode)
# ------------------------------------------
if app_mode == "📸 หน้าหลัก (ตรวจเช็คสิ่งของ)":
    st.title("🌐 ระบบตรวจเช็คสิ่งของอัจฉริยะ (Cloud Version)")
    st.write("---")

    ua = st_javascript("navigator.userAgent")
    is_mobile = False
    if ua:
        is_mobile = any(x in ua.lower() for x in ["android", "webos", "iphone", "ipad", "ipod", "blackberry", "iemobile", "opera mini"])

    col_input, col_result = st.columns([1.1, 1.0])

    with col_input:
        st.subheader("📷 นำเข้าภาพถ่าย")
        uploaded_file = None

        if is_mobile:
            uploaded_file = st.file_uploader(
                "📱 เปิดบนมือถือ: กดปุ่มด้านล่างแล้วเลือก 'ถ่ายภาพ' จากกล้องได้เลยครับ", 
                type=["jpg", "jpeg", "png"], 
                key="mobile_upload"
            )
        else:
            pc_mode = st.radio(
                "📂 เลือกรูปแบบการใช้งาน (สำหรับคอมพิวเตอร์):",
                ("💻 เปิดกล้องเว็บแคมสดเพื่อถ่ายภาพ", "📁 เลือกไฟล์รูปภาพจากในคอม"),
                horizontal=False
            )
            if "💻 เปิดกล้องเว็บแคมสด" in pc_mode:
                uploaded_file = st.camera_input("ส่องกล้องชูของให้เห็นชัดเจนแล้วกดถ่ายรูป")
            else:
                uploaded_file = st.file_uploader("📁 เลือกไฟล์ภาพจากเครื่อง (.jpg, .jpeg, .png)", type=["jpg", "jpeg", "png"], key="pc_file_upload")

    with col_result:
        st.subheader("📊 ผลการตรวจสอบความพร้อม")
        
        if uploaded_file is not None:
            image_raw = Image.open(uploaded_file)
            if hasattr(image_raw, '_getexif') and image_raw._getexif() is not None:
                from PIL import ImageOps
                image_raw = ImageOps.exif_transpose(image_raw)
            
            image_ai = image_raw.copy()
            found_objects = set()
            predictions = []
            
            with st.spinner("AI กำลังวิเคราะห์รูปภาพของคุณ..."):
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp_file:
                        image_raw.save(temp_file.name)
                        temp_path = temp_file.name
                        
                    result = client.infer(temp_path, model_id=model_id)
                    predictions = result.get("predictions", [])
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception as e:
                    st.error(f"เกิดข้อผิดพลาดในการประมวลผล AI: {e}")

            for pred in predictions:
                c_name = pred["class"].lower()
                if c_name in REQUIRED_CLASSES:
                    found_objects.add(c_name)

            is_all_present = all(cls in found_objects for cls in REQUIRED_CLASSES)
            
            if is_all_present:
                st.markdown('<div class="status-pass">🟢 PASS: ของครบถ้วน ออกเดินทางได้!</div>', unsafe_allow_html=True)
                st.balloons()
            else:
                st.markdown('<div class="status-fail">🔴 FAIL: ยังขาดของบางชิ้น!</div>', unsafe_allow_html=True)
                
            for cls in REQUIRED_CLASSES:
                display_name = CLASS_MAPPING_TH.get(cls, cls)
                if cls in found_objects:
                    st.markdown(f'<div class="item-box" style="background-color: #D4EDDA; color: #155724; border-left: 8px solid #28A745;">✅ {display_name}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="item-box" style="background-color: #F8D7DA; color: #721C24; border-left: 8px solid #DC3545;">❌ ยังไม่เจอ: {display_name}</div>', unsafe_allow_html=True)

            st.write("---")
            st.caption("🖼️ ภาพวิเคราะห์จาก AI:")
            
            draw = ImageDraw.Draw(image_ai)
            for pred in predictions:
                c_name = pred["class"]
                x, y, w, h = pred["x"], pred["y"], pred["width"], pred["height"]
                left, top, right, bottom = x - (w / 2), y - (h / 2), x + (w / 2), y + (h / 2)
                draw.rectangle([left, top, right, bottom], outline="#00E5FF", width=4)
                draw.text((left + 5, top + 5), f"{c_name}", fill="#00E5FF")
                
            st.image(image_ai, use_container_width=True)
            
            # ☁️ บันทึกไฟล์ขึ้น Google Drive อัตโนมัติ
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            status_str = "PASS" if is_all_present else "FAIL"
            base_filename = f"{timestamp}_{status_str}"
            
            with st.spinner("กำลังสำรองข้อมูลภาพและประวัติขึ้น Google Drive..."):
                with tempfile.TemporaryDirectory() as tmpdirname:
                    # 1. บันทึกและอัปโหลดภาพ Raw
                    raw_path = os.path.join(tmpdirname, f"{base_filename}_raw.jpg")
                    image_raw.save(raw_path)
                    upload_file_to_drive(raw_path, f"{base_filename}_raw.jpg", "image/jpeg")
                    
                    # 2. บันทึกและอัปโหลดภาพ AI
                    ai_path = os.path.join(tmpdirname, f"{base_filename}_ai.jpg")
                    image_ai.save(ai_path)
                    upload_file_to_drive(ai_path, f"{base_filename}_ai.jpg", "image/jpeg")
                    
                    # 3. บันทึกและอัปโหลดไฟล์ txt รายการสิ่งของ
                    txt_path = os.path.join(tmpdirname, f"{base_filename}.txt")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(",".join(list(found_objects)))
                    upload_file_to_drive(txt_path, f"{base_filename}.txt", "text/plain")
                    
                st.success("☁️ บันทึกข้อมูลและรูปภาพลง Google Drive สำเร็จเรียบร้อย!")
        else:
            st.info("💡 รอการถ่ายภาพหรืออัปโหลดรูปภาพ เพื่อเริ่มต้นวิเคราะห์ระบบ...")

# ------------------------------------------
# โหมดที่ 2: ข้อมูลระบบคลาวด์
# ------------------------------------------
else:
    st.title("📊 ข้อมูลระบบจัดเก็บข้อมูลบนคลาวด์")
    st.write("---")
    st.info("💡 เนื่องจากระบบนี้รันบน **Streamlit Community Cloud** (เพื่อเปิดใช้งานได้ 24 ชม. โดยไม่ต้องเปิดคอมพิวเตอร์) ภาพถ่ายและประวัติการตรวจสอบทั้งหมดจะถูกส่งตรงไปจัดเก็บไว้ใน **Google Drive** ที่คุณตั้งค่าเอาไว้โดยอัตโนมัติ คุณสามารถเข้าไปเปิดดูรูปภาพย้อนหลังได้จากใน Google Drive ของคุณโดยตรงเลยครับ!")