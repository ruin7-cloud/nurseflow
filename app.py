from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional, Dict, Any
import google.generativeai as genai
import json
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="NurseFlow Public API",
    description="AI-Powered Clinical Decision Support API. Supports auto-scaling with Server Key.",
    version="1.2.0"
)

SERVER_API_KEY = os.getenv("SERVER_GEMINI_KEY")

class AnalysisRequest(BaseModel):
    clinical_note: str

def safe_float(value):
    """Gelen veriyi güvenli bir şekilde float'a çevirir."""
    try:
        if value is None: return 0.0
        clean_val = str(value).replace(" mmHg", "").replace("/min", "").replace("°C", "").replace(",", ".")
        return float(clean_val)
    except (ValueError, TypeError):
        return 0.0

def calculate_news2_score(vitals: Dict[str, Any]):
    """
    NEWS2 Skorunu hesaplayan matematiksel motor.
    AI Halüsinasyonunu önlemek için Python if/else mantığı kullanır.
    """
    score = 0
    breakdown = []
    
    if not vitals:
        return 0, ["No data provided"]

    
    rr = safe_float(vitals.get('rr'))
    if rr > 0:
        if rr <= 8 or rr >= 25: 
            score += 3
            breakdown.append("RR Critical (<=8 or >=25)")
        elif rr >= 21: 
            score += 2
            breakdown.append("RR High (21-24)")
        elif rr <= 11: 
            score += 1
            breakdown.append("RR Low (9-11)")

    spo2 = safe_float(vitals.get('spo2'))
    if spo2 > 0:
        if spo2 <= 91: 
            score += 3
            breakdown.append("SpO2 Critical (<=91)")
        elif spo2 <= 93: 
            score += 2
            breakdown.append("SpO2 Low (92-93)")
        elif spo2 <= 95: 
            score += 1
            breakdown.append("SpO2 Mild (94-95)")

    sbp = safe_float(vitals.get('sbp'))
    if sbp > 0:
        if sbp <= 90: 
            score += 3
            breakdown.append("BP Low (<=90)")
        elif sbp >= 220: 
            score += 3
            breakdown.append("BP Critical High (>=220)") # NEWS2 modifiye
        elif sbp <= 100: 
            score += 2
            breakdown.append("BP Low (91-100)")
        elif sbp <= 110: 
            score += 1
            breakdown.append("BP Borderline (101-110)")

    hr = safe_float(vitals.get('hr'))
    if hr > 0:
        if hr <= 40 or hr >= 131: 
            score += 3
            breakdown.append("HR Critical (<=40 or >=131)")
        elif hr >= 111: 
            score += 2
            breakdown.append("HR High (111-130)")
        elif hr <= 50 or hr >= 91: 
            score += 1
            breakdown.append("HR Abnormal (41-50 or 91-110)")

    temp = safe_float(vitals.get('temp'))
    if temp > 0:
        if temp <= 35.0: 
            score += 3
            breakdown.append("Temp Hypothermia (<=35.0)")
        elif temp >= 39.1: 
            score += 2
            breakdown.append("Temp High (>=39.1)")
        elif temp <= 36.0 or temp >= 38.1: 
            score += 1
            breakdown.append("Temp Abnormal (35.1-36.0 or 38.1-39.0)")

    risk_label = "LOW RISK"
    if score >= 5: 
        risk_label = "HIGH RISK (Emergency Response)"
    elif score >= 3: 
        risk_label = "MEDIUM RISK (Urgent Review)"

    return score, risk_label, breakdown


@app.get("/")
def home():
    return {"message": "NurseFlow Public API is Active. Visit /docs for documentation."}

@app.post("/analyze/public")
def analyze_public(request: AnalysisRequest, x_user_key: Optional[str] = Header(None, alias="x-api-key")):
    """
    Klinik metni analiz eder ve NEWS2 skorunu hesaplar.
    
    Özellikler:
    - **API Key Esnekliği:** Kullanıcı kendi key'ini ('x-api-key' header ile) gönderebilir.
    - **Server Key:** Göndermezse, sunucunun tanımlı ücretsiz key'ini kullanır.
    """
    
    active_key = None
    used_key_source = "Unknown"

    if x_user_key:
        active_key = x_user_key
        used_key_source = "User Provided Key"
    elif SERVER_API_KEY:
        active_key = SERVER_API_KEY
        used_key_source = "Server Key (Free Tier)"
    else:
        raise HTTPException(status_code=500, detail="Server Configuration Error: No API Key available.")

    try:
        genai.configure(api_key=active_key)
        model = genai.GenerativeModel('gemini-2.5-flash-lite')
        
        prompt = f"""
        Act as a medical data parser. Extract vital signs from the text below into a JSON object.
        Keys required: 'sbp' (systolic bp), 'hr' (heart rate), 'rr' (respiration rate), 'spo2', 'temp'.
        Return ONLY valid JSON. Do not write markdown blocks.
        Text: {request.clinical_note}
        """
        
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        
        try:
            extracted_data = json.loads(response.text)
            if isinstance(extracted_data, list):
                extracted_data = extracted_data[0] if extracted_data else {}
        except json.JSONDecodeError:
            extracted_data = {}

        score, risk_label, details = calculate_news2_score(extracted_data)

        return {
            "meta": {
                "source": "NurseFlow API v1.2",
                "key_used": used_key_source
            },
            "analysis": {
                "original_text": request.clinical_note,
                "extracted_vitals": extracted_data
            },
            "result": {
                "news2_score": score,
                "risk_category": risk_label,
                "score_breakdown": details
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Processing Error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
