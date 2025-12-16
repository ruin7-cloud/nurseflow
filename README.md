# 🩺 NurseFlow Pro: AI-Powered Clinical Handover Assistant

**NurseFlow Pro** is a next-generation clinical decision support system designed to streamline nursing documentation, calculate risk scores accurately, and enhance patient safety using Generative AI.

## 🚀 Key Features

* **Hybrid AI Architecture:** Combines Google Gemini 2.5 Flash Lite with a Python-based logic engine to calculate **NEWS2 (National Early Warning Score)** mathematically, eliminating the risk of AI hallucinations in critical calculations.
* **Multimodal Data Intake:**
    * **📸 OCR Vision:** Instantly reads vital signs from patient monitor screens or handwritten notes.
    * **🎙️ Voice-to-Data:** Transcribes voice notes and automatically extracts structured clinical data (JSON).
    * **⌨️ Text Parsing:** Converts unstructured clinical notes into structured formats.
* **Automated Documentation:** Generates professional, GDPR-compliant **ISBAR (Identify, Situation, Background, Assessment, Recommendation)** handover reports in PDF format.
* **Privacy First:** Includes a dedicated "Privacy Mode" to anonymize patient data for security.

## 🛠️ Tech Stack & Architecture

* **Language:** Python 3.11
* **Frontend:** Streamlit (Custom CSS for UI/UX)
* **AI Model:** Google Gemini 2.5 Flash Lite (via `google-generativeai`)
* **Libraries:** * `fpdf` (Report Generation)
    * `Pillow` (Image Processing)
    * `streamlit-mic-recorder` (Audio Capture)
* **Pattern:** Logic-First AI (Data Extraction -> Rule-Based Calculation -> AI Reporting)

## 📦 How to Run

1. Clone the repository:
   ```bash
   git clone [https://github.com/ruin7-cloud/nurseflow-pro.git](https://github.com/ruin7-cloud/nurseflow-pro.git)
