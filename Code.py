import os
import json
import tempfile
from datetime import datetime
import streamlit as st
from PIL import Image, ImageDraw, ImageOps
from streamlit_javascript import st_javascript
from inference_sdk import InferenceHTTPClient

# Google Drive API Libraries
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# 1. ตั้งค่าหน้าตา UI ให้เรียบร้อย
st.set_page_config(page_title="Smart Check App", page_icon="🚪", layout="wide")

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
    /* สไตล์การ์ดแสดงผลฝั่งหลังบ้าน */
    .admin-card-present {
        color: #28a745; font-weight: bold; font-size: 14px; margin: 2px 0;
    }
    .admin-card-missing {
        color: #dc3545; font-weight: bold; font-size: 14px; margin: 2px 0;
    }
    </style>
""", unsafe_allow_html=True)

LOG_DIR = "backend_logs"

# ==========================================
# ☁️ ฟังก์ชันเชื่อมต่อและอัปโหลดเข้า Google Drive
# ==========================================
@st.cache_resource
def get_gdrive_service():
    """ดึงข้อมูล credentials จาก st.secrets แล้วสร้าง Drive API Service"""
    try:
        if "google_service_account" in st.secrets:
            # ดึงค่า Secrets ออกมาทำเป็น dict
            creds_dict = dict(st.secrets["google_service_account"])
            
            # จัดการแก้ไขปัญหา Format และเคลียร์ตัวอักษรขยะ \r ออก
            if "private_key" in creds_dict:
                pk = creds_dict["private_key"]
                
                # ลบ \r (Carriage Return) ของระบบ Windows ออกทันที
                pk = pk.replace("\r", "")
                
                # แปลง \n ที่ถูกเขียนแบบ string ตัวอักษรให้เป็นตัวขึ้นบรรทัดใหม่จริง
                pk = pk.replace("\\n", "\n")
                
                # เติม Header / Footer ถ้าถูกกลืนไป
                if not pk.startswith("-----BEGIN PRIVATE KEY-----"):
                    pk = "-----BEGIN PRIVATE KEY-----\n" + pk
                if not pk.endswith("-----END PRIVATE KEY-----"):
                    pk = pk + "\n-----END PRIVATE KEY-----"
                
                creds_dict["private_key"] = pk

            creds = service_account.Credentials.from_service_account_info(
                creds_dict,
                scopes=['https://www.googleapis.com/auth/drive.file']
            )
            return build('drive', 'v3', credentials=creds)
        else:
            return None
    except Exception as e:
        st.error(f"⚠️ เกิดข้อผิดพลาดในการเชื่อมต่อ Google Drive Service: {e}")
        return None
        
def upload_to_gdrive(file_path, file_name, folder_id):
    """ส่งไฟล์ที่กำหนดไปยัง Google Drive"""
    service = get_gdrive_service()
    if not service or not folder_id:
        return False
    
    try:
        file_metadata = {
            'name': 'filename.jpg',
            'parents': [GDRIVE_FOLDER_ID]
        }
        media = MediaFileUpload(file_path, resumable=True)
        uploaded_file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True  # <--- เพิ่มบรรทัดนี้ลงไป เพื่อให้รองรับ Shared Drive
        ).execute()
        return uploaded_file.get('id')
    except Exception as e:
        print(f"Error uploading {file_name} to Drive: {e}")
        return False

# 2. ฟังก์ชันโหลดโมเดล AI
@st.cache_resource
def load_model():
    api_key = st.secrets.get("ROBOFLOW_API_KEY", "xWM1igmZO9XPzWUoOmBc")
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
app_mode = st.sidebar.selectbox("เลือกหน้าเว็บที่ต้องการเข้าชม:", ["📸 หน้าหลัก (ตรวจเช็คสิ่งของ)", "📊 ระบบหลังบ้าน (สำหรับ Admin)"])

# ------------------------------------------
# โหมดที่ 1: หน้าหลักตรวจเช็คสิ่งของ (User Mode)
# ------------------------------------------
if app_mode == "📸 หน้าหลัก (ตรวจเช็คสิ่งของ)":
    st.title("🌐 ระบบตรวจเช็คสิ่งของอัจฉริยะ")
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
            # โหลดภาพดั้งเดิมไว้ (Raw Image)
            image_raw = Image.open(uploaded_file)
            if hasattr(image_raw, '_getexif') and image_raw._getexif() is not None:
                image_raw = ImageOps.exif_transpose(image_raw)
            
            # คัดลอกสร้างอีกรูปไว้สำหรับให้ AI วาดกรอบสี่เหลี่ยม (AI Image)
            image_ai = image_raw.copy()
            
            found_objects = set()
            predictions = []
            
            with st.spinner("AI กำลังวิเคราะห์รูปภาพของคุณ..."):
                try:
                    temp_path = "remote_scan_temp.jpg"
                    image_raw.save(temp_path)
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
            
            # วาดเส้นตำแหน่งลงบนภาพ AI
            draw = ImageDraw.Draw(image_ai)
            for pred in predictions:
                c_name = pred["class"]
                x, y, w, h = pred["x"], pred["y"], pred["width"], pred["height"]
                left, top, right, bottom = x - (w / 2), y - (h / 2), x + (w / 2), y + (h / 2)
                draw.rectangle([left, top, right, bottom], outline="#00E5FF", width=4)
                draw.text((left + 5, top + 5), f"{c_name}", fill="#00E5FF")
            
            # แสดงภาพที่สแกนแล้วบนหน้าแรก
            st.image(image_ai, use_container_width=True)
            
            # 📂 บันทึกรูปภาพลง Local Storage (ระบบหลังบ้าน)
            if not os.path.exists(LOG_DIR):
                os.makedirs(LOG_DIR)
                
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            status_str = "PASS" if is_all_present else "FAIL"
            base_filename = f"{timestamp}_{status_str}"
            
            filepath_raw = os.path.join(LOG_DIR, f"{base_filename}_raw.jpg")
            filepath_ai = os.path.join(LOG_DIR, f"{base_filename}_ai.jpg")
            txt_filepath = os.path.join(LOG_DIR, f"{base_filename}.txt")

            # 1. เซฟไฟล์ภาพธรรมดา (Raw)
            image_raw.save(filepath_raw)
            # 2. เซฟไฟล์ภาพพร้อมกรอบจับ (AI)
            image_ai.save(filepath_ai)
            # 3. เซฟไฟล์ประวัติของที่สแกนเจอ (.txt)
            with open(txt_filepath, "w", encoding="utf-8") as f:
                f.write(",".join(list(found_objects)))

            # ☁️ บันทึกลง Google Drive (ถ้าตั้งค่า GDRIVE_FOLDER_ID เอาไว้ใน Secrets)
            gdrive_folder_id = st.secrets.get("GDRIVE_FOLDER_ID", None)
            if gdrive_folder_id:
                with st.spinner("☁️ กำลังสำรองข้อมูลขึ้น Google Drive..."):
                    up_raw = upload_to_gdrive(filepath_raw, f"{base_filename}_raw.jpg", gdrive_folder_id)
                    up_ai = upload_to_gdrive(filepath_ai, f"{base_filename}_ai.jpg", gdrive_folder_id)
                    up_txt = upload_to_gdrive(txt_filepath, f"{base_filename}.txt", gdrive_folder_id)
                    
                    if up_raw and up_ai and up_txt:
                        st.toast("☁️ บันทึกรูปภาพและประวัติขึ้น Google Drive สำเร็จ!")
                    else:
                        st.toast("⚠️ ไม่สามารถบันทึกลง Google Drive ได้ (โปรดเช็คสิทธิ์และ Folder ID)")
        else:
            st.info("💡 รอการถ่ายภาพหรืออัปโหลดรูปภาพ เพื่อเริ่มต้นวิเคราะห์ระบบ...")

# ------------------------------------------
# โหมดที่ 2: ระบบจัดการหลังบ้านสำหรับ Admin (Admin Mode)
# ------------------------------------------
else:
    st.title("📊 ระบบจัดการและตรวจสอบประวัติหลังบ้าน")
    st.write("---")
    
    password = st.sidebar.text_input("🔑 ใส่รหัสผ่านเข้าหลังบ้าน:", type="password")
    
    if password != "admin1234":
        st.warning("🔒 กรุณากรอกรหัสผ่านที่ถูกต้องในแถบด้านข้าง (Sidebar) เพื่อเปิดเผยข้อมูลหลังบ้าน")
    else:
        if not os.path.exists(LOG_DIR) or len(os.listdir(LOG_DIR)) == 0:
            st.info("💡 ยังไม่มีข้อมูลประวัติการใช้งานในโฟลเดอร์หลังบ้าน")
        else:
            all_raw_files = [f for f in os.listdir(LOG_DIR) if f.lower().endswith('_raw.jpg')]
            all_raw_files.sort(reverse=True)
            
            total_scans = len(all_raw_files)
            pass_count = sum(1 for f in all_raw_files if "PASS" in f)
            fail_count = sum(1 for f in all_raw_files if "FAIL" in f)
            pass_rate = (pass_count / total_scans * 100) if total_scans > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📸 ตรวจเช็คทั้งหมด", f"{total_scans} ครั้ง")
            col2.metric("🟢 ผ่าน (PASS)", f"{pass_count} ครั้ง")
            col3.metric("🔴 ไม่ผ่าน (FAIL)", f"{fail_count} ครั้ง")
            col4.metric("📈 อัตราการผ่าน", f"{pass_rate:.1f}%")
            
            st.write("---")
            
            status_filter = st.selectbox("🔍 กรองสถานะข้อมูล:", ["ทั้งหมด (All)", "เฉพาะที่ผ่าน (PASS)", "เฉพาะที่ไม่ผ่าน (FAIL)"])
            
            if "PASS" in status_filter:
                filtered_files = [f for f in all_raw_files if "PASS" in f]
            elif "FAIL" in status_filter:
                filtered_files = [f for f in all_raw_files if "FAIL" in f]
            else:
                filtered_files = all_raw_files

            st.write(f"พบประวัติบันทึกข้อมูลทั้งหมด **{len(filtered_files)}** รายการ")
            
            cols_per_row = 4
            for i in range(0, len(filtered_files), cols_per_row):
                row_files = filtered_files[i:i+cols_per_row]
                cols = st.columns(cols_per_row)
                
                for idx, filename_raw in enumerate(row_files):
                    with cols[idx]:
                        base_prefix = filename_raw.replace("_raw.jpg", "")
                        
                        filepath_raw = os.path.join(LOG_DIR, filename_raw)
                        filepath_ai = os.path.join(LOG_DIR, f"{base_prefix}_ai.jpg")
                        txt_filepath = os.path.join(LOG_DIR, f"{base_prefix}.txt")
                        
                        items_found = []
                        if os.path.exists(txt_filepath):
                            with open(txt_filepath, "r", encoding="utf-8") as f:
                                content = f.read().strip()
                                if content:
                                    items_found = [item.strip().lower() for item in content.split(",")]
                        
                        try:
                            parts = base_prefix.split("_")
                            formatted_time = datetime.strptime(f"{parts[0]}_{parts[1]}", "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            formatted_time = "ไม่ทราบวันเวลา"
                        
                        is_pass = "PASS" in base_prefix
                        status_label = "🟢 PASS (ของครบ)" if is_pass else "🔴 FAIL (ของขาด)"
                        
                        tab_raw, tab_ai = st.tabs(["🖼️ ภาพจริง", "🤖 ภาพ AI"])
                        
                        with tab_raw:
                            if os.path.exists(filepath_raw):
                                st.image(Image.open(filepath_raw), use_container_width=True)
                        with tab_ai:
                            if os.path.exists(filepath_ai):
                                st.image(Image.open(filepath_ai), use_container_width=True)
                            else:
                                st.caption("ไม่มีภาพการตรวจจับแบบ AI")
                                
                        st.caption(f"📅 {formatted_time}")
                        st.markdown(f"### {status_label}")
                        
                        st.markdown("**🔍 รายการของที่ตรวจเจอ:**")
                        for cls in REQUIRED_CLASSES:
                            display_name = CLASS_MAPPING_TH.get(cls, cls)
                            if cls in items_found:
                                st.markdown(f'<div class="admin-card-present">✅ มี: {display_name}</div>', unsafe_allow_html=True)
                            else:
                                st.markdown(f'<div class="admin-card-missing">❌ ขาด: {display_name}</div>', unsafe_allow_html=True)
                        
                        st.write("") 
                        
                        if st.button("🗑️ ลบข้อมูล", key=f"del_{base_prefix}"):
                            if os.path.exists(filepath_raw): os.remove(filepath_raw)
                            if os.path.exists(filepath_ai): os.remove(filepath_ai)
                            if os.path.exists(txt_filepath): os.remove(txt_filepath)
                            st.toast(f"ลบชุดข้อมูลประวัตินี้เสร็จเรียบร้อย")
                            st.rerun()
