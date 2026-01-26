# services/ocr.py
import io
import pytesseract
from PIL import Image
from pdf2image import convert_from_bytes
from docx import Document
def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """
    Universal text extractor for Images, PDFs, and DOCX.
    """
    ext = filename.split('.')[-1].lower()
    
    try:
        # CASE 1: Images (JPG, PNG, JPEG)
        if ext in ['jpg', 'jpeg', 'png', 'bmp']:
            image = Image.open(io.BytesIO(file_bytes))
            return pytesseract.image_to_string(image)

        # CASE 2: PDF (Scanned or Digital)
        elif ext == 'pdf':
            # Convert PDF pages to images (requires poppler installed in Docker)
            images = convert_from_bytes(file_bytes)
            text = ""
            for i, image in enumerate(images):
                page_text = pytesseract.image_to_string(image)
                text += f"\n--- Page {i+1} ---\n{page_text}"
            return text

        # CASE 3: Word Documents (.docx)
        elif ext == 'docx':
            doc = Document(io.BytesIO(file_bytes))
            # Extract text from paragraphs
            full_text = [para.text for para in doc.paragraphs]
            return "\n".join(full_text)

        else:
            return f"Error: Unsupported file format '.{ext}'"

    except Exception as e:
        return f"Processing Error: {str(e)}"

def mock_ocr(file_bytes, filename):
    return extract_text_from_file(file_bytes, filename)
    """Mock OCR for demo purposes"""
    return "Democracy is a system of government by the whole population..."
