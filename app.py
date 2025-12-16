import streamlit as st
import google.generativeai as genai
import json
import os
from streamlit_mic_recorder import mic_recorder
from fpdf import FPDF
from PIL import Image

st.set_page_config(page_title="NurseFlow", page_icon="🩺", layout="wide")

st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; }
    .risk-card { padding: 20px; border-radius: 10px; color: white; text-align: center; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

MODEL_NAME = "gemini-2.5-flash-lite"

def safe_float(value):
    try:
        if value is None: return 0.0
        clean_val = str(value).replace(" mmHg", "").replace("/min", "").replace("°C", "").replace(",", ".")
        return float(clean_val)
    except (ValueError, TypeError):
        return 0.0

def create_pdf(report_text, news2_score, risk_label, vitals):
    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 15)
            self.cell(0, 10, 'NurseFlow - Clinical Handover Report', 0, 1, 'C')
            self.ln(5)
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, f"NEWS2 Score: {news2_score} ({risk_label})", ln=True)
    
    pdf.set_font("Arial", "", 10)
    if vitals:
        vitals_str = ", ".join([f"{k}: {v}" for k, v in vitals.items() if v is not None])
    else:
        vitals_str = "No extracted data."
    pdf.multi_cell(0, 10, f"Source Data: {vitals_str}")
    pdf.ln(5)
    
    pdf.set_font("Arial", "B", 12)
    pdf.cell(0, 10, "SBAR Assessment:", ln=True)
    pdf.ln(2)
    pdf.set_font("Arial", "", 11)
    safe_text = report_text.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 6, safe_text)
    return pdf.output(dest='S').encode('latin-1')

def calculate_news2_score(vitals):
    score = 0
    breakdown = []
    if not vitals: return 0, ["No data"]

    rr = safe_float(vitals.get('rr'))
    if rr > 0:
        if rr <= 8 or rr >= 25: score+=3; breakdown.append("RR Critical")
        elif rr >= 21: score+=2; breakdown.append("RR High")
        elif rr <= 11: score+=1; breakdown.append("RR Low")
        
    spo2 = safe_float(vitals.get('spo2'))
    if spo2 > 0:
        if spo2 <= 91: score+=3; breakdown.append("SpO2 Critical")
        elif spo2 <= 93: score+=2; breakdown.append("SpO2 Low")
        elif spo2 <= 95: score+=1; breakdown.append("SpO2 Mild")

    sbp = safe_float(vitals.get('sbp'))
    if sbp > 0:
        if sbp <= 90: score+=3; breakdown.append("BP Low")
        elif sbp >= 220: score+=3; breakdown.append("BP High")
        elif sbp <= 100: score+=2; breakdown.append("BP Low")
        elif sbp <= 110: score+=1; breakdown.append("BP Borderline")

    hr = safe_float(vitals.get('hr'))
    if hr > 0:
        if hr <= 40 or hr >= 131: score+=3; breakdown.append("HR Critical")
        elif hr >= 111: score+=2; breakdown.append("HR High")
        elif hr <= 50 or hr >= 91: score+=1; breakdown.append("HR Abnormal")

    temp = safe_float(vitals.get('temp'))
    if temp > 0:
        if temp <= 35.0: score+=3; breakdown.append("Temp Low")
        elif temp >= 39.1: score+=2; breakdown.append("Temp High")
        elif temp <= 36.0 or temp >= 38.1: score+=1; breakdown.append("Temp Abnormal")

    return score, breakdown

st.title("🩺 NurseFlow")
st.markdown("AI-Powered Clinical Decision Support System")

api_key = None
privacy_mode = True

try:
    if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
except (FileNotFoundError, KeyError, Exception):
    pass

if not api_key:
    with st.sidebar:
        st.header("🔑 Logim")
        st.warning("Password could not find.")
        api_key = st.text_input("Enter Gemini 2.5 Flash Lite API", type="password")
        privacy_mode = st.toggle("Privacy Mode (GDPR)", value=True)
else:
    with st.sidebar:
        st.success("✅ API Key took from system database")
        privacy_mode = st.toggle("Privacy Mode (GDPR)", value=True)

col_input, col_output = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("📥 Data Input")
    tab_text, tab_voice, tab_vision = st.tabs(["⌨️ Text", "🎙️ Voice", "📸 Vision"])
    
    final_source_type = None
    final_content = None

    with tab_text:
        text_input = st.text_area("Clinical Notes", height=150, placeholder="Patient vitals and observations...")

    with tab_voice:
        st.info("Click mic to record. AI will listen and extract data.")
        audio_input = mic_recorder(start_prompt="⏺️ Start Recording", stop_prompt="⏹️ Stop Recording", key='recorder')
        if audio_input:
            st.audio(audio_input['bytes'])
            final_content = audio_input['bytes']
            final_source_type = "audio"

    with tab_vision:
        uploaded_file = st.file_uploader("Upload Monitor Photo", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            image_data = Image.open(uploaded_file)
            st.image(image_data, caption="Uploaded Monitor", width=300)
            final_content = image_data
            final_source_type = "image"

    analyze_btn = st.button("🚀 Analyze Clinical Data", type="primary")

if analyze_btn and api_key:
    if not final_source_type and text_input:
        final_content = text_input
        final_source_type = "text"

    if not final_content:
        st.warning("Please provide Text, Audio, or Image input.")
        st.stop()

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        extracted_text_context = ""
        vitals = {}

        with st.spinner('🤖 Step 1: Processing Input...'):
            if final_source_type == "audio":
                with open("temp_audio.wav", "wb") as f: f.write(final_content)
                audio_file = genai.upload_file(path="temp_audio.wav")
                audio_prompt = "Extract vitals to JSON (sbp, hr, rr, spo2, temp) and context."
                response = model.generate_content([audio_prompt, audio_file], generation_config={"response_mime_type": "application/json"})
                result = json.loads(response.text)
                vitals = result.get("vitals", {})
                extracted_text_context = result.get("context", "Audio")
                if os.path.exists("temp_audio.wav"): os.remove("temp_audio.wav")

            elif final_source_type == "image":
                vision_prompt = "Extract vitals to JSON (sbp, hr, rr, spo2, temp) and context."
                response = model.generate_content([vision_prompt, final_content], generation_config={"response_mime_type": "application/json"})
                result = json.loads(response.text)
                vitals = result.get("vitals", {})
                extracted_text_context = result.get("context", "Image")

            elif final_source_type == "text":
                text_prompt = f"Extract vitals to JSON from: {final_content}"
                response = model.generate_content(text_prompt, generation_config={"response_mime_type": "application/json"})
                result = json.loads(response.text)
                vitals = result.get("vitals", {}) if isinstance(result, dict) else result
                extracted_text_context = final_content

            if isinstance(vitals, list): vitals = vitals[0] if vitals else {}

        with st.spinner('🧮 Step 2: Calculating Risk Score...'):
            news2_score, breakdown = calculate_news2_score(vitals)
            if news2_score >= 5: bg_color = "#e74c3c"; risk_txt = "HIGH RISK (Emergency)"
            elif news2_score >= 3: bg_color = "#f39c12"; risk_txt = "MEDIUM RISK"
            else: bg_color = "#27ae60"; risk_txt = "LOW RISK"

        with st.spinner('📝 Step 3: Generating Documentation...'):
            anonymize = "Use 'Patient X'" if privacy_mode else ""
            report_prompt = f"Write ISBAR report. Context: {extracted_text_context}. Vitals: {vitals}. NEWS2: {news2_score}. {anonymize}"
            report_res = model.generate_content(report_prompt)
            report_content = report_res.text

        with col_output:
            st.subheader("📊 Assessment Results")
            st.markdown(f'<div class="risk-card" style="background-color: {bg_color};"><h1 style="margin:0; font-size: 3em;">{news2_score}</h1><h3 style="margin:0;">{risk_txt}</h3></div>', unsafe_allow_html=True)
            
            res_tab1, res_tab2 = st.tabs(["📄 Report", "🔢 Vitals"])
            with res_tab1:
                st.text_area("Final Report", value=report_content, height=300)
                pdf_bytes = create_pdf(report_content, news2_score, risk_txt, vitals)
                st.download_button("📥 Download PDF", pdf_bytes, "report.pdf", "application/pdf")
            with res_tab2:
                st.json(vitals)

    except Exception as e:
        st.error(f"System Error: {e}")
