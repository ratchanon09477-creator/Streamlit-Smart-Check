import os
import tempfile
from datetime import datetime
import streamlit as st
from PIL import Image, ImageDraw
from roboflow import Roboflow
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ---------------------------------------------------------
# 1. การตั้งค่าหน้าเว็บ
# ---------------------------------------------------------
st.set_page_config(
    page_title="Smart Object Checker",
    page_icon="🔍",
    layout="centered"
)

st.title("🔍 ระบบตรวจเช็คสิ่งของอัตโนมัติ")
st.write("อัปโหลดรูปภาพหรือถ่ายรูปเพื่อตรวจเช็คสิ่งของและบันทึกประวัติลง Google Drive")

# ---------------------------------------------------------
# 2. โหลดโมเดล Roboflow (ใช้ SDK มาตรฐาน เสถียรกว่า)
# ---------------------------------------------------------
@st.cache_resource
def load_model():
    # ใส่ API Key ของคุณที่นี่ หรือดึงผ่าน st.secrets
    api_key = st.secrets.get("ROBOFLOW_API_KEY", "xWM1igmZO9XPzWUoOmBc")
    rf = Roboflow(api_key=api_key)
    project = rf.workspace().project("detect-object-dfq6s")
    model = project.version(15).model
    return model

try:
    model = load_model()
except Exception as e:
    st.error(f"ไม่สามารถเชื่อมต่อกับ Roboflow AI ได้: {e}")
    st.stop()

# ---------------------------------------------------------
# 3. การรับรูปภาพ (รองรับทั้งกล้องและไฟล์ โดยไม่ใช้ JavaScript)
# ---------------------------------------------------------
st.subheader("📷 เลือกวิธีนำเข้ารูปภาพ")

tab1, tab2 = st.tabs(["📸 ถ่ายรูปจากกล้อง", "📁 อัปโหลดไฟล์รูปภาพ"])

image_input = None

with tab1:
    camera_file = st.camera_input("ถ่ายรูปสิ่งของที่ต้องการตรวจเช็ค")
    if camera_file:
        image_input = camera_file

with tab2:
    uploaded_file = st.file_uploader("เลือกรูปภาพจากเครื่อง (JPG, PNG)", type=["jpg", "jpeg", "png"])
    if uploaded_file:
        image_input = uploaded_file

# ---------------------------------------------------------
# 4. ประมวลผลเมื่อมีรูปภาพเข้ามา
# ---------------------------------------------------------
if image_input is not None:
    # แปลงไฟล์เป็น PIL Image
    image = Image.open(image_input)
    st.image(image, caption="รูปภาพที่นำเข้า", use_container_width=True)

    if st.button("🚀 เริ่มตรวจเช็คสิ่งของ", type="primary"):
        with st.spinner("กำลังวิเคราะห์รูปภาพด้วย AI..."):
            # บันทึกรูปชั่วคราวเพื่อส่งให้ Roboflow
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                image.save(tmp_file.name)
                tmp_path = tmp_file.name

            try:
                # ส่งรูปไปให้ AI วิเคราะห์
                prediction = model.predict(tmp_path, confidence=40, overlap=30).json()
                predictions = prediction.get("predictions", [])

                # วาดกรอบสี่เหลี่ยมบนรูปภาพ
                draw = ImageDraw.Draw(image)
                detected_items = []

                for pred in predictions:
                    label = pred["class"]
                    confidence = pred["confidence"]
                    x = pred["x"]
                    y = pred["y"]
                    width = pred["width"]
                    height = pred["height"]

                    # คำนวณพิกัดมุมซ้ายบน และขวาล่าง
                    left = x - (width / 2)
                    top = y - (height / 2)
                    right = x + (width / 2)
                    bottom = y + (height / 2)

                    # วาดกรอบสีแดง
                    draw.rectangle([left, top, right, bottom], outline="red", width=3)
                    draw.text((left, max(0, top - 10)), f"{label} ({confidence:.2f})", fill="red")
                    detected_items.append(label)

                # แสดงผลลัพธ์
                st.success("✅ ตรวจวิเคราะห์เสร็จสิ้น!")
                st.image(image, caption="ผลลัพธ์การตรวจเช็ค", use_container_width=True)

                if detected_items:
                    st.write("**สิ่งของที่ตรวจพบ:**", ", ".join(set(detected_items)))
                else:
                    st.info("ไม่พบสิ่งของที่ระบุในระบบ")

            except Exception as e:
                st.error(f"เกิดข้อผิดพลาดในการประมวลผล: {e}")
            finally:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)

# ---------------------------------------------------------
# 5. สรุปไฟล์ requirements.txt ที่ต้องใช้ควบคู่กัน
# ---------------------------------------------------------
# อย่าลืมปรับไฟล์ requirements.txt บน GitHub ให้เหลือเพียงเท่านี้:
# streamlit
# roboflow
# pillow
# google-api-python-client
# google-auth-httplib2
# google-auth-oauthlib