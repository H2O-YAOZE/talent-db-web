import pdfplumber

def read_pdf_text(file_path, max_pages=5):
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                t = page.extract_text()
                if t: text += t + "\n\n"
    except Exception as e:
        text = f"[PDF 读取失败: {str(e)}]"
    return text.strip()
