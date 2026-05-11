"""Auto-classify uploaded PDF as resume or paper using LLM."""
from llm import call_llm, parse_json_from_llm
from pdf_reader import read_pdf_text

def classify_file(file_path):
    """Read first 3 pages, ask LLM to classify. Returns 'resume' or 'paper'."""
    text = read_pdf_text(file_path, max_pages=3)
    if not text:
        return "resume"  # default

    prompt = f"""请判断以下文本来自"简历"还是"学术论文"。只返回一个单词：resume 或 paper。

文本（前3页）：
{text[:3000]}

回复格式：只返回 resume 或 paper"""

    result = call_llm(prompt)
    if not result:
        # Fallback: keyword check
        keywords_paper = ["abstract", "introduction", "conclusion", "references", "et al", "proposed", "method", "experiment", "contribution", "related work"]
        keywords_resume = ["工作经历", "教育经历", "教育背景", "实习", "自我评价", "技能", "联系方式", "邮箱", "电话", "work experience", "education", "skills", "phone", "email"]
        text_lower = text.lower()
        paper_score = sum(1 for k in keywords_paper if k in text_lower)
        resume_score = sum(1 for k in keywords_resume if k in text_lower)
        return "paper" if paper_score > resume_score else "resume"

    result = result.strip().lower()
    if "paper" in result or "论文" in result:
        return "paper"
    return "resume"
