import os
import fitz # PyMuPDF
import pdfplumber
import io
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv
import json
import streamlit as st
from fpdf import FPDF
import base64

# --- Configuration ---
load_dotenv()

# Load API key from environment variables
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
except KeyError:
    st.error("FATAL: GOOGLE_API_KEY environment variable not set. Please set it to your Gemini API key.")
    st.stop()

# --- Prompts ---
TEXT_PROMPT = """
You are an expert accounts payable specialist. Your task is to analyze the following text content from an invoice and a purchase order and extract key information.

From the INVOICE text, extract:
- Invoice Number
- Date
- Vendor Name
- A list of all line items. Each item should have a 'description', 'quantity', and 'price'.
- Total Amount

From the PURCHASE ORDER text, extract:
- PO Number
- Date
- Vendor Name
- A list of all ordered items. Each item should have a 'description', 'quantity', and 'price'.
- Total Amount

Return your findings ONLY as a single, minified JSON object. The JSON structure must be:
{
  "invoice_data": {
    "invoice_no": "...", "date": "...", "vendor": "...",
    "items": [{"description": "...", "quantity": 1, "price": 0.00}],
    "total": 0.00
  },
  "po_data": {
    "po_no": "...", "date": "...", "vendor": "...",
    "items": [{"description": "...", "quantity": 1, "price": 0.00}],
    "total": 0.00
  }
}
"""

IMAGE_PROMPT = """
You are an expert accounts payable specialist. Your task is to extract key information from the provided document images.

From the INVOICE image, extract:
- Invoice Number
- Date
- Vendor Name
- A list of all line items. Each item should have a 'description', 'quantity', and 'price'.
- Total Amount

From the PURCHASE ORDER image, extract:
- PO Number
- Date
- Vendor Name
- A list of all ordered items. Each item should have a 'description', 'quantity', and 'price'.
- Total Amount

Return your findings ONLY as a single, minified JSON object. The JSON structure must be:
{
  "invoice_data": {
    "invoice_no": "...", "date": "...", "vendor": "...",
    "items": [{"description": "...", "quantity": 1, "price": 0.00}],
    "total": 0.00
  },
  "po_data": {
    "po_no": "...", "date": "...", "vendor": "...",
    "items": [{"description": "...", "quantity": 1, "price": 0.00}],
    "total": 0.00
  }
}
"""

# --- Gemini API Interaction ---
def get_gemini_response(payload):
    # Determine the model based on the payload content
    if any(isinstance(item, Image.Image) for item in payload):
        model_name = 'gemini-2.5-pro'
    else:
        model_name = 'gemini-2.5-pro'

    model = genai.GenerativeModel(model_name)
    try:
        generation_config = genai.types.GenerationConfig(temperature=0)
        response = model.generate_content(payload, generation_config=generation_config)
        # Clean up the response text before parsing
        json_text = response.text.strip()
        # Handle cases where the model might return the JSON in a code block
        if json_text.startswith('```json'):
            json_text = json_text[7:-3].strip()
        elif json_text.startswith('```'):
            json_text = json_text[3:-3].strip()
        
        return json.loads(json_text)
    except json.JSONDecodeError:
        st.error("Failed to decode JSON from Gemini response. Please check the response format.")
        st.write("Raw Gemini response:", response.text if 'response' in locals() else "No response object")
        return {}
    except Exception as e:
        st.error(f"An error occurred with the Gemini API: {e}")
        # It's helpful to see the raw response when debugging
        if 'response' in locals():
            st.write("Raw Gemini response for debugging:", response.text)
        return {}

# --- Helpers ---
def get_text_with_pdfplumber(file):
    try:
        with pdfplumber.open(file) as pdf:
            text = "\n".join([page.extract_text() for page in pdf.pages if page.extract_text()])
        return text.strip()
    except Exception as e:
        print(f"pdfplumber failed: {e}")
        return ""

def prepare_image(file):
    if not file.name.lower().endswith('.pdf'):
        return Image.open(file)
    try:
        doc = fitz.open(stream=file.read(), filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_data = pix.tobytes("png")
        doc.close()
        return Image.open(io.BytesIO(img_data))
    except Exception as e:
        st.error(f"Failed to convert PDF to image: {e}")
        st.stop()

def create_pdf(json_data):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size = 12)
    pdf.multi_cell(0, 10, txt = json.dumps(json_data, indent=4))
    return pdf.output(dest='S').encode('latin-1')

def editable_display_doc(title, data, doc_type):
    with st.container():
        st.subheader(title)
        data[f'{doc_type.lower()}_no'] = st.text_input(f"{doc_type.capitalize()} Number", value=data.get(f'{doc_type.lower()}_no', 'N/A'), key=f"{doc_type}_no")
        data['vendor'] = st.text_input("Vendor", value=data.get('vendor', 'N/A'), key=f"{doc_type}_vendor")
        data['total'] = st.number_input("Total Amount", value=float(data.get('total', 0.0)), key=f"{doc_type}_total")
        
        with st.expander("View Itemized Details"):
            items = data.get("items", [])
            if items:
                edited_items = st.data_editor(items, key=f"{doc_type}_items")
                data['items'] = edited_items
            else:
                st.info("No items found.")
    return data

# --- Streamlit UI ---
st.set_page_config(page_title="SMART-Match", layout="wide")

# --- Style ---
def load_css():
    st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap');
        body {
            font-family: 'Roboto', sans-serif;
        }
        .stApp {
            background-color: #0e1117;
            background-image: url("https://www.transparenttextures.com/patterns/3d-casio.png");
            color: white;
        }
        .stApp .card {
            background-color: #1e1e1e;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        }
        .stApp section[data-testid="stSidebar"] {
            background-color: white !important;
            color: black;
        }
        .stApp .stMetric label, .stApp .stMetric div {
            color: white;
        }
        .stApp .stButton > button {
            background-color: #4CAF50;
            color: white;
            padding: 12px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            box-shadow: 0 5px #999;
            transition: all 0.1s ease-in-out;
        }
        .stApp .stButton > button:hover {
            background-color: #45a049;
        }
        .stApp .stButton > button:active {
            background-color: #45a049;
            box-shadow: 0 2px #666;
            transform: translateY(4px);
        }
        .stApp .stDownloadButton > button {
            background-color: #4CAF50;
            color: white;
        }
        .stFileUploader label {
            color: black !important;
        }
        .st-emotion-cache-1vzeuhh {
            color: black !important;
        }
        [data-testid="stToolbar"] button {
            color: white !important;
        }
    </style>
    """, unsafe_allow_html=True)

load_css()

# --- Sidebar ---
with st.sidebar:
    st.title("Invoice Matcher")
    st.write("Upload an invoice and its corresponding purchase order to automatically compare them.")
    
    invoice_file = st.file_uploader(" Upload Invoice", type=["pdf", "png", "jpg", "jpeg"])
    po_file = st.file_uploader(" Upload Purchase Order", type=["pdf", "png", "jpg", "jpeg"])

    compare_button = st.button("View Matching", use_container_width=True)

# --- Main App ---
st.title("SMART-Match: AI-Powered Invoice & PO Reconciliation")
st.write("Welcome to the future of automated invoice processing! Upload your documents and let our AI do the heavy lifting.")

st.divider()

if compare_button:
    if invoice_file is None or po_file is None:
        st.error("Please upload both an Invoice and a Purchase Order file.")
        st.stop()

    with st.spinner("🤖 Analyzing documents..."):
        # --- Document Analysis ---
        invoice_text = get_text_with_pdfplumber(invoice_file)
        po_text = get_text_with_pdfplumber(po_file)

        # Reset file pointers
        invoice_file.seek(0)
        po_file.seek(0)

        if invoice_text and po_text:
            st.info("✅ Using text-based extraction.")
            payload = [TEXT_PROMPT, f"\n--- INVOICE TEXT ---\n{invoice_text}", f"\n--- PO TEXT ---\n{po_text}"]
            analysis = get_gemini_response(payload)
        else:
            st.warning("⚠ Text extraction failed. Falling back to image-based analysis.")
            invoice_image = prepare_image(invoice_file)
            po_image = prepare_image(po_file)
            payload = [IMAGE_PROMPT, invoice_image, po_image]
            analysis = get_gemini_response(payload)

    st.success("Analysis complete!")

    invoice_data = analysis.get('invoice_data', {})
    po_data = analysis.get('po_data', {})

    if 'invoice_data' not in st.session_state:
        st.session_state.invoice_data = invoice_data
    if 'po_data' not in st.session_state:
        st.session_state.po_data = po_data

    # --- Results Tabs ---
    st.subheader("📋 Analysis Results")
    tab1, tab2, tab3 = st.tabs(["✅ Match Summary", "📄 Invoice", "📑 Purchase Order"])

    with tab1:
        recalculate = st.button("Recalculate Match")
        if recalculate:
            st.session_state.invoice_data = st.session_state.edited_invoice_data
            st.session_state.po_data = st.session_state.edited_po_data

        match_status = "✅ APPROVED: Perfect Match!"
        if not (st.session_state.invoice_data.get('vendor') == st.session_state.po_data.get('vendor') and abs(float(st.session_state.invoice_data.get('total', 0.0)) - float(st.session_state.po_data.get('total', 0.0))) < 0.01):
            match_status = "⚠ NEEDS REVIEW: Discrepancies found."
        st.info(match_status)

        st.markdown("For a detailed breakdown, please see the Invoice and Purchase Order tabs.")
        st.markdown("### 📦 Raw JSON Result")

        
        pdf_bytes = create_pdf(analysis)
        st.download_button(
            label="Download JSON as PDF",
            data=pdf_bytes,
            file_name="analysis.pdf",
            mime="application/pdf",
        )

    with tab2:
        with st.container():
            st.session_state.edited_invoice_data = editable_display_doc("📄 Invoice Details", st.session_state.invoice_data, "invoice")

    with tab3:
        with st.container():
            st.session_state.edited_po_data = editable_display_doc("📑 Purchase Order Details", st.session_state.po_data, "po")
            
    st.divider()
    
    # --- Document Preview ---
    st.subheader("📄 Document Preview")
    doc_preview_tabs = st.tabs(["Invoice", "Purchase Order"])
    with doc_preview_tabs[0]:
        st.image(prepare_image(invoice_file), use_container_width=True)
    with doc_preview_tabs[1]:
        st.image(prepare_image(po_file), use_container_width=True)
