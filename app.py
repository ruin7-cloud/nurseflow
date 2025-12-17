import streamlit as st
import google.generativeai as genai
import json
import os
from streamlit_mic_recorder import mic_recorder
from fpdf import FPDF
from PIL import Image

st.set_page_config(page_title="NurseFlow Pro v3.2 (Debug)", page_icon="🩺", layout="wide")

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
        clean_val = str(value).lower().replace("mmhg", "").replace("/min", "").replace("bpm", "").replace("°c", "").replace("%", "").strip()
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
    vitals_str = json.dumps(vitals, indent=2) 
    pdf.multi_cell(0, 10, f"Extracted Vitals: {vitals_str}")
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
    
    if not isinstance(vitals, dict):
        return 0, ["Error: Data format issue"]

    rr = safe_float(vitals.get('rr'))
    if rr > 0:
        if rr <= 8 or rr >= 25: score+=3; breakdown.append(f"RR Critical ({rr})")
        elif rr >= 21: score+=2; breakdown.append(f"RR High ({rr})")
        elif rr <= 11: score+=1; breakdown.append(f"RR Low ({rr})")
        
    spo2 = safe_float(vitals.get('spo2'))
    if spo2 > 0:
        if spo2 <= 91: score+=3; breakdown.append(f"SpO2 Critical ({spo2})")
        elif spo2 <= 93: score+=2; breakdown.append(f"SpO2 Low ({spo2})")
        elif spo2 <= 95: score+=1; breakdown.append(f"SpO2 Mild ({spo2})")

    sbp = safe_float(vitals.get('sbp'))
    if sbp > 0:
        if sbp <= 90: score+=3; breakdown.append(f"BP Low ({sbp})")
        elif sbp >= 220: score+=3; breakdown.append(f"BP High ({sbp})")
        elif sbp <= 100: score+=2; breakdown.append(f"BP Low ({sbp})")
        elif sbp <= 110: score+=1; breakdown.append(f"BP Borderline ({sbp})")

    hr = safe_float(vitals.get('hr'))
    if hr > 0:
        if hr <= 40 or hr >= 131: score+=3; breakdown.append(f"HR Critical ({hr})")
        elif hr >= 111: score+=2; breakdown.append(f"HR High ({hr})")
        elif hr <= 50 or hr >= 91: score+=1; breakdown.append(f"HR Abnormal ({hr})")

    temp = safe_float(vitals.get('temp'))
    if temp > 0:
        if temp <= 35.0: score+=3; breakdown.append(f"Temp Low ({temp})")
        elif temp >= 39.1: score+=2; breakdown.append(f"Temp High ({temp})")
        elif temp <= 36.0 or temp >= 38.1: score+=1; breakdown.append(f"Temp Abnormal ({temp})")

    return score, breakdown

st.title("🩺 NurseFlow Pro v3.2 (Fix)")

api_key = None
privacy_mode = True

try:
    if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
except:
    pass

if not api_key:
    with st.sidebar:
        st.header("🔑 Giriş")
        api_key = st.text_input("Gemini API Key", type="password")
        privacy_mode = st.toggle("Privacy Mode (GDPR)", value=True)
else:
    with st.sidebar:
        st.success("✅ API Key Sistemden Alındı")
        privacy_mode = st.toggle("Privacy Mode (GDPR)", value=True)

col_input, col_output = st.columns([1, 1], gap="large")

with col_input:
    st.subheader("📥 Data Input")
    tab_text, tab_voice, tab_vision = st.tabs(["⌨️ Text", "🎙️ Voice", "📸 Vision"])
    
    final_source_type = None
    final_content = None

    with tab_text:
        text_input = st.text_area("Clinical Notes", height=150, placeholder="Patient vitals...")
    with tab_voice:
        audio_input = mic_recorder(start_prompt="⏺️ Rec", stop_prompt="⏹️ Stop", key='recorder')
        if audio_input:
            final_content = audio_input['bytes']
            final_source_type = "audio"
    with tab_vision:
        uploaded_file = st.file_uploader("Upload Monitor", type=["jpg", "png", "jpeg"])
        if uploaded_file:
            final_content = Image.open(uploaded_file)
            st.image(final_content, width=300)
            final_source_type = "image"

    analyze_btn = st.button("🚀 Analyze", type="primary")

if analyze_btn and api_key:
    if not final_source_type and text_input:
        final_content = text_input
        final_source_type = "text"

    if not final_content:
        st.warning("Lütfen veri giriniz.")
        st.stop()

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(MODEL_NAME)
        vitals = {}
        extracted_text_context = ""

        strict_instruction = """
        You are a medical data parser. 
        TASK: Extract vital signs into a STRICT JSON format.
        
        REQUIRED JSON KEYS (Exact spelling):
        - "sbp" (Systolic Blood Pressure - ONLY the first number, e.g., 120)
        - "hr" (Heart Rate)
        - "rr" (Respiration Rate)
        - "spo2" (Oxygen Saturation)
        - "temp" (Temperature)
        
        RULES:
        1. Return ONLY the JSON object. No markdown, no intro text.
        2. Use numeric values (int or float). Do not include units like "mmHg".
        3. If a value is missing, use null.
        """

        with st.spinner('🤖 Step 1: Processing...'):
            if final_source_type == "text":
                prompt = f"{strict_instruction}\n\nTEXT TO ANALYZE:\n{final_content}"
                response = model.generate_content(prompt)
                raw_text = response.text
                extracted_text_context = final_content
                
            elif final_source_type == "image":
                prompt = f"{strict_instruction}\n\nAnalyze this image."
                response = model.generate_content([prompt, final_content])
                raw_text = response.text
                extracted_text_context = "Image Analysis"
                
            elif final_source_type == "audio":
                with open("temp.wav", "wb") as f: f.write(final_content)
                a_file = genai.upload_file("temp.wav")
                prompt = f"{strict_instruction}\n\nListen to this audio."
                response = model.generate_content([prompt, a_file])
                raw_text = response.text
                extracted_text_context = "Audio Analysis"

            cleaned_text = raw_text.replace("```json", "").replace("```", "").strip()
            vitals = json.loads(cleaned_text)
            
            if isinstance(vitals, list): vitals = vitals[0]

        with st.spinner('🧮 Step 2: Calculating...'):
            news2_score, breakdown = calculate_news2_score(vitals)
            
            if news2_score >= 5: color = "#e74c3c"; risk = "HIGH RISK"
            elif news2_score >= 3: color = "#f39c12"; risk = "MEDIUM RISK"
            else: color = "#27ae60"; risk = "LOW RISK"

        with st.spinner('📝 Step 3: Reporting...'):
            anonymize = "Use 'Patient X'" if privacy_mode else ""
            rep_prompt = f"Write ISBAR report. Vitals: {vitals}. Score: {news2_score}. {anonymize}"
            rep_res = model.generate_content(rep_prompt)

        with col_output:
            with st.expander("🛠️ DEBUGGER (AI Verisi)", expanded=True):
                st.write("AI'dan Gelen Ham Veri:")
                st.json(vitals)
                st.write("Ceza Puanları:")
                st.write(breakdown)

            st.markdown(f'<div class="risk-card" style="background-color: {color};"><h1>{news2_score}</h1><h3>{risk}</h3></div>', unsafe_allow_html=True)
            
            res_tab1, res_tab2 = st.tabs(["📄 Rapor", "⬇️ PDF İndir"])
            with res_tab1:
                st.text_area("Final Report", value=rep_res.text, height=300)
            with res_tab2:
                pdf_bytes = create_pdf(rep_res.text, news2_score, risk, vitals)
                st.download_button("📥 Download PDF", pdf_bytes, "report.pdf", "application/pdf")

    except Exception as e:
        st.error(f"Hata: {e}")
