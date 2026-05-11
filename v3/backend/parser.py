"""Resume and paper parsing via LLM + GitHub search."""
import json, os
from llm import call_llm, parse_json_from_llm
from pdf_reader import read_pdf_text
from github_search import search_github_author
from database import get_db

# ── Paper parsing ──

def process_paper(file_path):
    text = read_pdf_text(file_path, max_pages=5)
    prompt = f"""请从以下论文文本中提取信息，只返回 JSON 对象，不要其他文字。

论文文本（前5页）：
{text[:8000]}

返回格式：
```json
{{"title": "论文标题", "team": "团队/机构名称", "direction": "研究方向关键词，3-5个英文关键词，逗号分隔", "abstract_summary": "一句话概括论文核心贡献（中文，50字以内）", "authors": [{{"name": "作者姓名", "email": "邮箱（如无则null）", "institution": "机构/学校", "research_field": "研究方向关键词", "is_intern": false}}]}}
```
is_intern: 根据作者标注的图标或身份判断，实习/学生填 true，正式员工/研究员填 false，不确定填 false。"""

    result = call_llm(prompt)
    if not result: return {"error": "LLM 调用失败"}

    try: info = parse_json_from_llm(result)
    except: return {"error": f"JSON 解析失败: {result[:200]}"}

    authors = info.get("authors") or []
    valid_authors = []
    for a in authors:
        if not isinstance(a, dict): continue
        name = (a.get("name") or "").strip()
        if not name or len(name) > 50 or "author list" in name.lower() or "contribution" in name.lower():
            continue
        github_info = search_github_author(a)
        if github_info:
            a["github_username"] = github_info.get("github_username", "")
            a["github_url"] = github_info.get("github_url", "")
            a["match_confidence"] = github_info.get("match_confidence", "unmatched")
        else:
            a["github_username"] = ""; a["github_url"] = ""; a["match_confidence"] = "unmatched"
        valid_authors.append(a)

    info["authors"] = valid_authors
    return info


def save_paper_result(file_path, info):
    if not info.get("title"): return
    conn = get_db()
    fn = os.path.basename(file_path).replace(".pdf", "")
    title = info.get("title", fn)
    team = info.get("team", "")
    direction = info.get("direction", "")
    summary = info.get("abstract_summary", "")

    existing = conn.execute("SELECT id FROM papers WHERE file_path=?", (file_path,)).fetchone()
    if existing:
        conn.execute("UPDATE papers SET title=?, team=?, upload_time=datetime('now','localtime') WHERE id=?",
                     (title, team, existing["id"]))
        paper_id = existing["id"]
    else:
        conn.execute("INSERT INTO papers (title, file_path, team) VALUES (?,?,?)", (title, file_path, team))
        paper_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute("UPDATE papers SET raw_data=? WHERE id=?",
                 (json.dumps({"direction": direction, "summary": summary}, ensure_ascii=False), paper_id))

    for a in info.get("authors") or []:
        if not a.get("name"): continue
        ex = conn.execute("SELECT id, github_username FROM candidates WHERE name=? AND source='paper'", (a["name"],)).fetchone()
        if ex:
            gh = a.get("github_username", "")
            if gh and not ex["github_username"]:
                conn.execute("UPDATE candidates SET github_username=?, github_url=?, match_confidence=?, paper_id=?, institution=?, research_field=?, updated_at=datetime('now','localtime') WHERE id=?",
                             (gh, a.get("github_url"), a.get("match_confidence"), paper_id, a.get("institution"), a.get("research_field"), ex["id"]))
            else:
                conn.execute("UPDATE candidates SET paper_id=? WHERE id=?", (paper_id, ex["id"]))
        else:
            conn.execute("""INSERT INTO candidates (name, email, institution, research_field, github_username, github_url, match_confidence, source, paper_id, status)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                         (a["name"], a.get("email"), a.get("institution"), a.get("research_field"),
                          a.get("github_username"), a.get("github_url"), a.get("match_confidence"), "paper", paper_id, "active"))
    conn.commit()
    conn.close()
    return paper_id


# ── Resume parsing ──

def process_resume(file_path, fallback_name=""):
    text = read_pdf_text(file_path, max_pages=10)

    # Include filename hint in prompt if available
    name_hint = ""
    if fallback_name:
        name_hint = f"\n注意：此简历的文件名为「{fallback_name}」，如正文无法提取姓名，请以此为候选人姓名。"

    prompt = f"""你是一个技术猎头。请从以下简历中提取结构化信息。只返回 JSON 对象，不要其他文字。缺失字段填 null。
如果正文中找不到姓名，name 字段请留空字符串 ""，不要猜。{name_hint}

简历文本：
{text[:10000]}

返回格式：
```json
{{
  "name": "姓名",
  "email": "邮箱",
  "phone": "电话",
  "degree": "最高学位（本科/硕士/博士）",
  "institution": "最后学校",
  "education": [{{"school": "学校", "degree": "学位", "major": "专业", "year": "年份"}}],
  "work_experience": [{{"company": "公司", "role": "职位", "duration": "时长"}}],
  "skills": ["技能1", "技能2"],
  "github_username": "GitHub用户名（如简历中提到）",
  "github_url": "GitHub个人主页链接（如简历中提到）",
  "research_field": "研究方向/工作领域",
  "social_links": [{{"platform": "平台名(如小红书/微博/知乎/LinkedIn/个人网站等)", "url": "链接"}}]
}}
```"""

    result = call_llm(prompt)
    if not result: return {"name": fallback_name, "error": "LLM 调用失败，使用文件名"}
    try: info = parse_json_from_llm(result)
    except: return {"name": fallback_name, "error": f"JSON 解析失败: {result[:200]}"}

    # Name resolution: LLM > fallback (filename) > empty
    if not info.get("name") and fallback_name:
        info["name"] = fallback_name

    # GitHub: if not found in resume text, search actively
    if not info.get("github_url") and not info.get("github_username"):
        author_info = {
            "name": info.get("name", ""),
            "email": info.get("email", ""),
            "institution": info.get("institution", ""),
        }
        gh_result = search_github_author(author_info)
        if gh_result:
            info["github_username"] = gh_result.get("github_username", "")
            info["github_url"] = gh_result.get("github_url", "")
            info["match_confidence"] = gh_result.get("github_match", "medium")

    # Sanitize GitHub URL: ensure it's a profile URL, not a repo URL
    gh_url = info.get("github_url", "")
    if gh_url and "github.com" in gh_url:
        parts = gh_url.split("github.com/")[-1].split("/")
        if parts and parts[0]:
            info["github_url"] = f"https://github.com/{parts[0]}"
            if not info.get("github_username"):
                info["github_username"] = parts[0]

    # Store social links as JSON
    social_links = info.pop("social_links", []) or []
    if social_links:
        info["social_links"] = json.dumps(social_links, ensure_ascii=False)

    # Dedup: name + email + phone
    conn = get_db()
    name = info.get("name", "")
    email = info.get("email", "")
    phone = info.get("phone", "")
    existing = None
    if email:
        existing = conn.execute("SELECT id FROM candidates WHERE email=? AND source='resume'", (email,)).fetchone()
    if not existing and phone:
        existing = conn.execute("SELECT id FROM candidates WHERE phone=? AND source='resume'", (phone,)).fetchone()
    if not existing and name:
        existing = conn.execute("SELECT id FROM candidates WHERE name=? AND source='resume'", (name,)).fetchone()

    education_json = json.dumps(info.get("education", []), ensure_ascii=False)
    work_json = json.dumps(info.get("work_experience", []), ensure_ascii=False)
    skills_json = json.dumps(info.get("skills", []), ensure_ascii=False)
    degree = info.get("degree", "")

    if existing:
        conn.execute("""UPDATE candidates SET email=?, phone=?, degree=?, institution=?, education=?, work_experience=?, skills=?,
            github_username=?, github_url=?, research_field=?, source='resume', updated_at=datetime('now','localtime')
            WHERE id=?""",
                     (email, phone, degree, info.get("institution"), education_json, work_json, skills_json,
                      info.get("github_username"), info.get("github_url"), info.get("research_field"), existing["id"]))
    else:
        conn.execute("""INSERT INTO candidates (name, email, phone, degree, institution, education, work_experience, skills,
            github_username, github_url, research_field, source, match_confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'resume', 'manual', 'active')""",
                     (name, email, phone, degree, info.get("institution"), education_json, work_json, skills_json,
                      info.get("github_username"), info.get("github_url"), info.get("research_field")))
    conn.commit()
    conn.close()
    return info
