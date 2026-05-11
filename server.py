#!/usr/bin/env python3
"""
🎯 人才数据库 Web 版 v2
核心功能：
  1. 上传论文 → 自动提取作者信息，搜索 GitHub，写入表格
  2. 上传简历 → 自动解析结构化信息，写入表格
启动：python3 server.py
访问：http://localhost:8080
"""

import json, os, sqlite3, hashlib, uuid, shutil, time, re, cgi, subprocess, sys
import traceback
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ==================== 配置 ====================
HOST = "0.0.0.0"
PORT = 8080
DB_PATH = os.path.expanduser(os.getenv("TALENT_DB_PATH", "~/projects/talent-db/data/talent.db"))
UPLOAD_DIR = os.path.expanduser(os.getenv("TALENT_UPLOAD_DIR", "~/projects/talent-db/input"))
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_FILE = os.path.join(DATA_DIR, "index.html")
SECRET_KEY = os.getenv("TALENT_SECRET_KEY", "talent-db-2026")
LLM_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
LLM_MODEL = os.getenv("TALENT_LLM_MODEL", "qwen-max")
LLM_API_KEY = os.getenv("TALENT_LLM_API_KEY", "")
LLM_MAX_CHARS = 25000

# ==================== LLM 调用 ====================
def call_llm(prompt, max_retries=2):
    """调用 LLM API，返回文本"""
    if not LLM_API_KEY:
        import sys; print("  [LLM] API Key 未配置")
        return None
    # 截断超长输入
    max_chars = 25000
    if len(prompt) > max_chars:
        prompt = prompt[:max_chars] + "\n\n[文本已截断]"
    import requests as req
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LLM_API_KEY}"
    }
    payload = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 4096,
        "temperature": 0.1
    }
    print(f"  [LLM] 调用 model={LLM_MODEL}, prompt长度={len(prompt)}")
    for attempt in range(max_retries + 1):
        try:
            resp = req.post(f"{LLM_BASE_URL}/chat/completions", headers=headers,
                          json=payload, timeout=120)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                err = resp.text[:300]
                print(f"  [LLM] HTTP {resp.status_code}: {err}")
                if resp.status_code in (400, 401, 403):
                    return None  # 不可恢复错误
                if attempt < max_retries:
                    time.sleep(3)
        except Exception as e:
            print(f"  [LLM] 异常: {e}")
            if attempt < max_retries:
                time.sleep(2)
    return None

# ==================== PDF 读取 ====================
def read_pdf_text(file_path, max_pages=5):
    """读取 PDF 前 N 页文本"""
    import pdfplumber
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages[:max_pages]):
                t = page.extract_text()
                if t:
                    text += t + "\n\n"
    except Exception as e:
        text = f"[PDF 读取失败: {str(e)}]"
    return text.strip()

# ==================== 论文处理 ====================
def process_paper(file_path):
    """处理论文：提取标题+团队+研究方向 + 提取作者并搜索 GitHub"""
    print(f"  📄 处理论文: {os.path.basename(file_path)}")

    # 读前 5 页（作者列表可能在第 1-5 页的 Contributions 部分）
    text = read_pdf_text(file_path, max_pages=5)

    # Step 1: 提取论文信息 + 作者
    prompt = f"""请从以下论文文本中提取信息，只返回 JSON 对象，不要其他文字。

论文文本（前5页）：
{text[:8000]}

返回格式：
```json
{{"title": "论文标题", "team": "团队/机构名称", "direction": "研究方向关键词，3-5个英文关键词，逗号分隔", "abstract_summary": "一句话概括论文核心贡献（中文，50字以内）", "authors": [{{"name": "作者姓名", "email": "邮箱（如无则null）", "institution": "机构/学校", "research_field": "研究方向关键词"}}]}}
```"""

    result = call_llm(prompt)
    if not result:
        return {"error": "LLM 调用失败"}

    try:
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if m:
            info = json.loads(m.group())
        else:
            info = json.loads(result)
    except:
        return {"error": f"JSON 解析失败: {result[:200]}"}

    print(f"    ✓ {info.get('title','')} | 方向: {info.get('direction','')}")

    # Step 2: 为每个作者搜索 GitHub（过滤无效作者）
    authors = info.get("authors") or []
    valid_authors = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = (author.get("name") or "").strip()
        # 过滤掉占位文字
        if not name or len(name) > 50 or "author list" in name.lower() or "contribution" in name.lower():
            continue
        valid_authors.append(author)

    for author in valid_authors:
        github_info = search_github_author(author)
        if github_info:
            author["github_username"] = github_info.get("github_username", "")
            author["github_url"] = github_info.get("github_url", "")
            author["match_confidence"] = github_info.get("match_confidence", "unmatched")
        else:
            author["github_username"] = ""
            author["github_url"] = ""
            author["match_confidence"] = "unmatched"
        print(f"    → {author['name']} GitHub: {author['github_username'] or '未找到'}")

    info["authors"] = valid_authors
    return info

def _save_paper_result(file_path, info):
    """将论文解析结果写入 papers 表 + 作者写入 candidates 表"""
    if not info.get("title"):
        return
    conn = get_db()
    fn = os.path.basename(file_path).replace(".pdf", "")
    title = info.get("title", fn)
    team = info.get("team", "")
    direction = info.get("direction", "")
    summary = info.get("abstract_summary", "")

    # 查重（按文件路径）
    existing = conn.execute("SELECT id FROM papers WHERE file_path=?", (file_path,)).fetchone()
    if existing:
        conn.execute("UPDATE papers SET title=?, team=?, upload_time=datetime('now','localtime') WHERE id=?",
                    (title, team, existing["id"]))
        paper_id = existing["id"]
    else:
        conn.execute("INSERT INTO papers (title, file_path, team) VALUES (?,?,?)", (title, file_path, team))
        paper_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # 保存方向和摘要
    conn.execute("UPDATE papers SET raw_data=? WHERE id=?",
                (json.dumps({"direction": direction, "summary": summary}, ensure_ascii=False), paper_id))

    # 保存作者到 candidates
    authors = info.get("authors") or []
    for a in authors:
        if not a.get("name"):
            continue
        # 查重
        ex = conn.execute("SELECT id, github_username FROM candidates WHERE name = ? AND source = 'paper'", (a["name"],)).fetchone()
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

def search_github_author(author):
    """用 GitHub API 搜索作者的 GitHub 账号"""
    name = (author.get("name") or "").strip()
    email = (author.get("email") or "").strip()
    institution = (author.get("institution") or "").strip()
    if not name and not email:
        return None

    import requests as req

    # 构建搜索词，优先用邮箱（精确），其次用名字
    queries = []
    if email:
        queries.append(email)  # 邮箱搜索最精确
    if name:
        # 名字去掉空格
        compact = name.replace(" ", "")
        queries.append(compact)
        if " " in name:
            queries.append(name.replace(" ", "+"))

    seen = set()
    for q in queries:
        try:
            url = f"https://api.github.com/search/users?q={req.utils.quote(q)}&per_page=5"
            resp = req.get(url, timeout=10, headers={"Accept": "application/vnd.github.v3+json"})
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("items", []):
                    login = item.get("login", "")
                    if login in seen:
                        continue
                    seen.add(login)

                    # 获取用户详情
                    detail = req.get(f"https://api.github.com/users/{login}", timeout=10,
                                    headers={"Accept": "application/vnd.github.v3+json"})
                    if detail.status_code == 200:
                        u = detail.json()
                        # 匹配验证：至少 2 项证据
                        evidence = []
                        if email and u.get("email", "").lower() == email.lower():
                            evidence.append("邮箱匹配")
                        # 名字匹配（忽略大小写和连字符）
                        gh_name = (u.get("name") or "").lower().replace("-", "").replace(" ", "")
                        author_name = name.lower().replace("-", "").replace(" ", "")
                        if gh_name and author_name and (author_name in gh_name or gh_name in author_name):
                            evidence.append("姓名匹配")
                        # 机构匹配
                        gh_company = (u.get("company") or "").lower()
                        inst = institution.lower()
                        if gh_company and inst and (inst in gh_company or gh_company in inst):
                            evidence.append("机构匹配")
                        # 位置匹配
                        gh_loc = (u.get("location") or "").lower()
                        if gh_loc and inst and (inst[:2] in gh_loc or gh_loc[:2] in inst):
                            evidence.append("地区匹配")

                        confidence = "unmatched"
                        if len(evidence) >= 2:
                            confidence = "high"
                        elif len(evidence) >= 1:
                            confidence = "medium"

                        if confidence != "unmatched":
                            return {
                                "github_username": login,
                                "github_url": u.get("html_url", f"https://github.com/{login}"),
                                "github_match": confidence
                            }
        except:
            pass
    return None

# ==================== 简历处理 ====================
def process_resume(file_path):
    """处理简历：提取结构化信息"""
    print(f"  📋 处理简历: {os.path.basename(file_path)}")

    text = read_pdf_text(file_path, max_pages=10)

    prompt = f"""你是一个技术猎头。请从以下简历中提取结构化信息。
只返回 JSON 对象，不要其他文字。缺失字段填 null。

简历文本：
{text[:10000]}

返回格式：
```json
{{
  "name": "姓名",
  "email": "邮箱",
  "phone": "电话",
  "institution": "最后学校",
  "education": [{{"school": "学校", "degree": "学位", "major": "专业", "year": "年份"}}],
  "work_experience": [{{"company": "公司", "role": "职位", "duration": "时长"}}],
  "skills": ["技能1", "技能2"],
  "github_username": "GitHub用户名（如简历中提到）",
  "github_url": "GitHub链接",
  "research_field": "研究方向/工作领域"
}}
```"""

    result = call_llm(prompt)
    if not result:
        return {"error": "LLM 调用失败"}

    try:
        m = re.search(r'\{.*\}', result, re.DOTALL)
        if m:
            info = json.loads(m.group())
        else:
            info = json.loads(result)
    except:
        return {"error": f"JSON 解析失败: {result[:200]}"}

    if not info.get("name"):
        return {"error": "未提取到姓名"}

    # 写入数据库
    conn = get_db()
    name = info.get("name", "")
    email = info.get("email", "")

    # 查重
    existing = None
    if email:
        existing = conn.execute("SELECT id FROM candidates WHERE email = ?", (email,)).fetchone()
    if not existing and name:
        existing = conn.execute("SELECT id FROM candidates WHERE name = ?", (name,)).fetchone()

    education_json = json.dumps(info.get("education", []), ensure_ascii=False)
    work_json = json.dumps(info.get("work_experience", []), ensure_ascii=False)
    skills_json = json.dumps(info.get("skills", []), ensure_ascii=False)

    if existing:
        conn.execute("""
            UPDATE candidates SET email=?, phone=?, institution=?, education=?, work_experience=?, skills=?,
            github_username=?, github_url=?, research_field=?, source='resume', updated_at=datetime('now','localtime')
            WHERE id=?
        """, (email, info.get("phone"), info.get("institution"), education_json, work_json, skills_json,
              info.get("github_username"), info.get("github_url"), info.get("research_field"), existing["id"]))
        print(f"    ↻ 更新已有记录: {name}")
    else:
        conn.execute("""
            INSERT INTO candidates (name, email, phone, institution, education, work_experience, skills,
            github_username, github_url, research_field, source, match_confidence, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'resume', 'manual', 'active')
        """, (name, email, info.get("phone"), info.get("institution"), education_json, work_json, skills_json,
              info.get("github_username"), info.get("github_url"), info.get("research_field")))
        print(f"    + 新增记录: {name}")

    conn.commit()
    conn.close()
    return info

# ==================== 处理队列（后台线程） ====================
process_queue = []
process_executor = ThreadPoolExecutor(max_workers=2)

def process_file_task(file_path, task_type):
    """后台处理文件"""
    try:
        if task_type == "paper":
            result = process_paper(file_path)
            if not result.get("error"):
                _save_paper_result(file_path, result)
        else:
            result = process_resume(file_path)
            if result.get("name"):
                conn = get_db()
                conn.execute("UPDATE candidates SET source_file=? WHERE name=? AND source='resume' AND source_file IS NULL",
                           (file_path, result["name"]))
                conn.commit()

        # 更新任务状态
        conn = get_db()
        status = "done" if not result.get("error") else "failed"
        conn.execute("UPDATE task_queue SET status=?, finished_at=datetime('now','localtime'), error_message=? WHERE file_path=?",
                    (status, result.get("error", ""), file_path))
        conn.commit()
        conn.close()
        return result
    except Exception as e:
        traceback.print_exc()
        conn = get_db()
        conn.execute("UPDATE task_queue SET status='failed', finished_at=datetime('now','localtime'), error_message=? WHERE file_path=?",
                    (str(e), file_path))
        conn.commit()
        conn.close()
        return {"error": str(e)}

def submit_process(file_path, task_type):
    """提交处理任务到线程池"""
    # 更新状态为 processing
    conn = get_db()
    conn.execute("UPDATE task_queue SET status='processing', started_at=datetime('now','localtime') WHERE file_path=?", (file_path,))
    conn.commit()
    conn.close()
    process_executor.submit(process_file_task, file_path, task_type)

# ==================== 数据库 ====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def ensure_tables():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT DEFAULT 'user',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS candidates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT, phone TEXT,
            institution TEXT,
            education TEXT,
            work_experience TEXT,
            skills TEXT,
            github_username TEXT, github_url TEXT, research_field TEXT,
            source TEXT,
            match_confidence TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'active',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS task_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL, task_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending', retry_count INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            started_at TEXT, finished_at TEXT,
            uploaded_by TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_c_email ON candidates(email);
        CREATE INDEX IF NOT EXISTS idx_c_name ON candidates(name);
        CREATE INDEX IF NOT EXISTS idx_c_source ON candidates(source);
        CREATE INDEX IF NOT EXISTS idx_c_github ON candidates(github_username);
    """)
    # 安全添加列
    for col in ["uploaded_by TEXT", "paper_id INTEGER", "source_file TEXT", "raw_data TEXT", "tags TEXT", "summary TEXT"]:
        try:
            conn.execute(f"ALTER TABLE candidates ADD COLUMN {col}")
        except:
            pass
    # 论文分组表
    conn.execute("""CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT, file_path TEXT, team TEXT,
        upload_time TEXT DEFAULT (datetime('now','localtime')),
        uploaded_by TEXT
    )""")
    for col in ["raw_data TEXT", "uploaded_by TEXT"]:
        try:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {col}")
        except:
            pass
            pass

    conn.execute("""CREATE TABLE IF NOT EXISTS feedback (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        author TEXT,
        created_at TEXT DEFAULT (datetime('now','localtime'))
    )""")
    # 默认管理员
    try:
        pw = hashlib.sha256(f"admin{SECRET_KEY}".encode()).hexdigest()
        conn.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')", (pw,))
    except:
        pass
    conn.commit()
    conn.close()

def hash_password(pw):
    return hashlib.sha256(f"{pw}{SECRET_KEY}".encode()).hexdigest()

# ==================== Sessions ====================
_sessions = {}
def create_session(username):
    token = str(uuid.uuid4())
    _sessions[token] = {"username": username, "created": time.time()}
    return token
def get_user(token):
    s = _sessions.get(token)
    if s and time.time() - s["created"] < 86400:
        return s["username"]
    return None

# ==================== HTTP Handler ====================
class Handler(SimpleHTTPRequestHandler):
    def _json(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False, default=str).encode())

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return self.rfile.read(n) if n else b""

    def _url(self):
        p = urlparse(self.path)
        return p.path, parse_qs(p.query)

    def _auth(self):
        t = self.headers.get("Authorization", "").replace("Bearer ", "")
        u = get_user(t)
        if not u:
            self._json({"error": "未登录"}, 401)
            return None
        return u

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
        self.end_headers()

    def do_GET(self):
        path, params = self._url()
        routes = {
            "/api/auth/me": self._api_me,
            "/api/papers": lambda p: self._api_papers(p),
            "/api/resumes": lambda p: self._api_list("resume", p),
            "/api/tasks": lambda p: self._api_tasks(p),
            "/api/feedback": lambda p: self._api_feedback_get(p),
            "/api/clear/papers": lambda: self._api_clear_papers(),
            "/api/clear/resumes": lambda: self._api_clear_resumes(),
        }
        # 候选人详情
        if path.startswith("/api/candidates/"):
            self._api_candidate_detail(path[len("/api/candidates/"):])
            return
        # 文件下载
        if path.startswith("/api/download/"):
            self._api_download(path[len("/api/download/"):])
            return
        h = routes.get(path)
        if h:
            h(params)
        elif path in ("/", "/index.html"):
            self._serve_html()
        else:
            self._json({"error": "Not found"}, 404)

    def do_POST(self):
        path, _ = self._url()
        routes = {
            "/api/auth/login": self._api_login,
            "/api/auth/register": self._api_register,
            "/api/upload": self._api_upload,
            "/api/feedback": self._api_feedback_post,
            "/api/process/pending": self._api_process_pending,
        }
        h = routes.get(path)
        if h:
            h()
        else:
            self._json({"error": "Not found"}, 404)

    # ==================== 文件删除 API ====================

    def _api_feedback_post(self):
        user = self._auth()
        if not user: return
        try:
            data = json.loads(self._body())
            content = data.get("content", "").strip()
            if not content:
                self._json({"error": "内容不能为空"}, 400)
                return
            conn = get_db()
            conn.execute("INSERT INTO feedback (content, author) VALUES (?, ?)", (content, user))
            conn.commit()
            conn.close()
            self._json({"ok": True})
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _api_feedback_get(self):
        user = self._auth()
        if not user: return
        conn = get_db()
        rows = conn.execute("SELECT * FROM feedback ORDER BY created_at DESC LIMIT 50").fetchall()
        conn.close()
        self._json({"data": [dict(r) for r in rows]})

    def do_DELETE(self):
        path, _ = self._url()
        user = self._auth()
        if not user: return

        if path.startswith("/api/file/"):
            # 删除源文件 + 数据库记录
            file_id = path[len("/api/file/"):]
            conn = get_db()
            row = conn.execute("SELECT file_path, task_type FROM task_queue WHERE id=?", (file_id,)).fetchone()
            if row:
                fp, ft = row["file_path"], row["task_type"]
                if os.path.exists(fp):
                    os.remove(fp)
                    conn.execute("DELETE FROM candidates WHERE source=? AND raw_data LIKE ?", (ft, '%' + os.path.basename(fp) + '%'))
                conn.execute("DELETE FROM task_queue WHERE id=?", (file_id,))
            # 也删除关联的论文分组
            conn.execute("DELETE FROM papers WHERE file_path=? OR file_path=(SELECT file_path FROM task_queue WHERE id=?)", (fp, file_id))
            conn.commit()
            conn.close()
            self._json({"ok": True})

        elif path.startswith("/api/candidates/"):
            cid = path.split("/")[-1]
            conn = get_db()
            conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
            conn.commit()
            conn.close()
            self._json({"ok": True})

        elif path.startswith("/api/paper/"):
            # 删除论文分组 + 源文件 + 所有候选人
            paper_id = path[len("/api/paper/"):]
            conn = get_db()
            paper = conn.execute("SELECT file_path FROM papers WHERE id=?", (paper_id,)).fetchone()
            if paper:
                fp = paper["file_path"]
                if os.path.exists(fp):
                    os.remove(fp)
                conn.execute("DELETE FROM candidates WHERE paper_id=?", (paper_id,))
                conn.execute("DELETE FROM task_queue WHERE file_path=?", (fp,))
                conn.execute("DELETE FROM papers WHERE id=?", (paper_id,))
            conn.commit()
            conn.close()
            self._json({"ok": True})

        else:
            self._json({"error": "Not found"}, 404)

    def _serve_html(self):
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(f.read().encode())

    def _api_login(self):
        try:
            data = json.loads(self._body())
            conn = get_db()
            u = conn.execute("SELECT * FROM users WHERE username=?", (data["username"],)).fetchone()
            conn.close()
            if u and u["password_hash"] == hash_password(data["password"]):
                self._json({"token": create_session(data["username"]), "username": data["username"], "role": u["role"]})
            else:
                self._json({"error": "用户名或密码错误"}, 401)
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _api_register(self):
        try:
            data = json.loads(self._body())
            conn = get_db()
            try:
                conn.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (data["username"], hash_password(data["password"])))
                conn.commit()
                self._json({"token": create_session(data["username"]), "username": data["username"], "role": "user"})
            except sqlite3.IntegrityError:
                self._json({"error": "用户名已存在"}, 400)
            finally:
                conn.close()
        except Exception as e:
            self._json({"error": str(e)}, 400)

    def _api_me(self):
        user = self._auth()
        if not user: return
        self._json({"username": user})

    def _api_upload(self):
        user = self._auth()
        if not user: return
        # 上传大小限制 50MB
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 50 * 1024 * 1024:
            self._json({"error": "文件过大，最大 50MB"}, 413)
            return
        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                               environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": self.headers["Content-Type"]})
        task_type = form.getvalue("type", "paper")
        files = form["files"] if isinstance(form["files"], list) else [form["files"]]
        conn = get_db()
        results = []
        # 限制同时排队任务数
        pending_count = conn.execute("SELECT COUNT(*) FROM task_queue WHERE status IN ('pending','processing')").fetchone()[0]
        if pending_count >= 10:
            conn.close()
            self._json({"error": "处理队列已满（最多10个），请等待当前任务完成"}, 429)
            return
        for f in files:
            if not f.filename:
                continue
            # 检查 pending 中是否有同名文件（去重）
            existing = conn.execute("SELECT status FROM task_queue WHERE file_path LIKE ? AND status IN ('pending','processing')",
                                   ('%' + f.filename,)).fetchone()
            if existing:
                results.append({"file": f.filename, "type": task_type, "path": "skipped（已有相同文件在处理中）"})
                continue
            ext = os.path.splitext(f.filename)[1].lower()
            save_dir = os.path.join(UPLOAD_DIR, task_type + "s")
            safe_name = f"{int(time.time())}_{f.filename}"
            save_path = os.path.join(save_dir, safe_name)
            with open(save_path, "wb") as out:
                out.write(f.file.read())
            conn.execute("INSERT INTO task_queue (file_path, task_type, status, uploaded_by) VALUES (?, ?, 'pending', ?)",
                       (save_path, task_type, user))
            results.append({"file": f.filename, "type": task_type, "path": save_path})
        conn.commit()
        conn.close()
        self._json({"results": results})

    def _api_process_pending(self):
        """手动触发处理所有 pending 任务"""
        user = self._auth()
        if not user: return
        conn = get_db()
        rows = conn.execute("SELECT file_path, task_type FROM task_queue WHERE status='pending' ORDER BY created_at ASC").fetchall()
        conn.close()
        count = 0
        for r in rows:
            submit_process(r["file_path"], r["task_type"])
            count += 1
        self._json({"processing": count})

    def _api_papers(self, params):
        """论文列表（含作者和 GitHub 信息）"""
        user = self._auth()
        if not user: return
        conn = get_db()
        kw = params.get("keyword", [""])[0]
        if kw:
            where = "WHERE p.title LIKE ? OR p.team LIKE ? OR p.raw_data LIKE ?"
            vals = [f"%{kw}%"] * 2 + [f"%{kw}%"]
        else:
            where = ""
            vals = []
        papers = conn.execute(f"SELECT p.* FROM papers p {where} ORDER BY p.upload_time DESC", vals).fetchall()
        data = []
        for p in papers:
            raw = {}
            try: raw = json.loads(p["raw_data"]) if p["raw_data"] else {}
            except: pass
            # 获取关联作者
            authors = conn.execute("""SELECT id, name, email, institution, research_field,
                github_username, github_url, match_confidence
                FROM candidates WHERE paper_id = ? AND source = 'paper'""", (p["id"],)).fetchall()
            author_list = [{"id": a["id"], "name": a["name"], "email": a["email"],
                "institution": a["institution"], "research_field": a["research_field"],
                "github_username": a["github_username"], "github_url": a["github_url"],
                "match_confidence": a["match_confidence"]} for a in authors]
            task = conn.execute("SELECT t.id FROM task_queue t WHERE t.file_path = ?", (p["file_path"],)).fetchone()
            data.append({
                "id": p["id"], "title": p["title"], "file_path": p["file_path"],
                "team": p["team"], "upload_time": p["upload_time"],
                "direction": raw.get("direction", ""),
                "summary": raw.get("summary", ""),
                "authors": author_list,
                "task_id": task["id"] if task else None
            })
        conn.close()
        self._json({"total": len(data), "data": data})

    def _api_clear_papers(self):
        user = self._auth()
        if not user: return
        conn = get_db()
        paths = conn.execute("SELECT file_path FROM papers").fetchall()
        for r in paths:
            if r[0] and os.path.exists(r[0]):
                os.remove(r[0])
        conn.execute("DELETE FROM candidates WHERE source='paper'")
        conn.execute("DELETE FROM papers")
        task_paths = conn.execute("SELECT file_path FROM task_queue WHERE task_type='paper'").fetchall()
        conn.execute("DELETE FROM task_queue WHERE task_type='paper'")
        conn.commit(); conn.close()
        self._json({"ok": True})

    def _api_clear_resumes(self):
        user = self._auth()
        if not user: return
        conn = get_db()
        paths = conn.execute("SELECT file_path FROM task_queue WHERE task_type='resume'").fetchall()
        for r in paths:
            if r[0] and os.path.exists(r[0]):
                os.remove(r[0])
        conn.execute("DELETE FROM candidates WHERE source='resume'")
        conn.execute("DELETE FROM task_queue WHERE task_type='resume'")
        conn.commit(); conn.close()
        self._json({"ok": True})

    def _api_candidate_detail(self, cid):
        user = self._auth()
        if not user: return
        conn = get_db()
        row = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
        conn.close()
        if not row:
            self._json({"error": "Not found"}, 404)
            return
        d = dict(row)
        for f in ["education", "work_experience", "skills"]:
            try: d[f] = json.loads(d[f]) if d[f] else []
            except: d[f] = []
        self._json(d)

    def _api_download(self, file_id):
        """下载源文件"""
        user = self._auth()
        if not user: return
        conn = get_db()
        row = conn.execute("SELECT file_path FROM task_queue WHERE id=?", (file_id,)).fetchone()
        conn.close()
        if not row or not os.path.exists(row["file_path"]):
            self._json({"error": "文件不存在"}, 404)
            return
        fp = row["file_path"]
        fname = os.path.basename(fp)
        import mimetypes
        from urllib.parse import quote
        mime = mimetypes.guess_type(fname)[0] or "application/octet-stream"
        with open(fp, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(fname))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_list(self, source, params):
        user = self._auth()
        if not user: return
        conn = get_db()
        page = int(params.get("page", ["1"])[0])
        size = int(params.get("size", ["50"])[0])
        kw = params.get("keyword", [""])[0]

        where = ["c.status='active'", "c.source=?"]
        sql_params = [source]
        if kw:
            where.append("(c.name LIKE ? OR c.email LIKE ? OR c.institution LIKE ? OR c.research_field LIKE ? OR c.github_username LIKE ?)")
            k = f"%{kw}%"
            sql_params.extend([k, k, k, k, k])

        wc = " AND ".join(where)
        total = conn.execute(f"SELECT COUNT(*) FROM candidates c WHERE {wc}", sql_params).fetchone()[0]
        rows = conn.execute(f"""
            SELECT c.*, t.id as task_id
            FROM candidates c
            LEFT JOIN task_queue t ON t.file_path = c.source_file
            WHERE {wc} ORDER BY c.created_at DESC LIMIT ? OFFSET ?
        """, sql_params + [size, (page-1)*size]).fetchall()
        conn.close()
        data = []
        for r in rows:
            d = dict(r)
            for f in ["education", "work_experience", "skills"]:
                try: d[f] = json.loads(d[f]) if d[f] else []
                except: d[f] = []
            data.append(d)
        self._json({"total": total, "page": page, "data": data})

    def _api_tasks(self, params):
        user = self._auth()
        if not user: return
        conn = get_db()
        rows = conn.execute("SELECT * FROM task_queue ORDER BY created_at DESC LIMIT 50").fetchall()
        conn.close()
        self._json({"data": [dict(r) for r in rows]})


# ==================== 启动 ====================
import sys
if __name__ == "__main__":
    ensure_tables()
    # 强制 unbuffered 输出 + UTF-8（Windows GBK 终端兼容）
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    print("\n🎯 人才数据库 Web 版 v2 启动中...")
    # 自动处理已有的 pending 任务
    conn = get_db()
    pending = conn.execute("SELECT file_path, task_type FROM task_queue WHERE status='pending'").fetchall()
    conn.close()
    if pending:
        print(f"  ⏳ 发现 {len(pending)} 个待处理任务，自动开始处理...")
        for r in pending:
            submit_process(r["file_path"], r["task_type"])
    print(f"""
╔══════════════════════════════════════════╗
║  🎯 人才数据库 v2                      ║
║  http://localhost:{PORT}                   ║
║  账号: admin / admin                    ║
║                                        ║
║  功能:                                  ║
║  1. 上传论文 → 自动搜索 GitHub 作者    ║
║  2. 上传简历 → 自动解析结构化信息      ║
╚══════════════════════════════════════════╝
""")
    server = HTTPServer((HOST, PORT), Handler)
    server.serve_forever()
