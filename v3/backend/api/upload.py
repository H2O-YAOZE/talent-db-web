import os, time, json, re
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, UploadFile, File, Form
from database import get_db
from config import UPLOAD_DIR
from classifier import classify_file
from parser import process_paper, save_paper_result, process_resume
from api.auth import get_user

router = APIRouter(prefix="/api", tags=["upload"])
executor = ThreadPoolExecutor(max_workers=2)

def extract_name_from_filename(filename):
    """Extract a candidate name from filename. E.g. '姚杰个人简历.pdf' → '姚杰'"""
    # Remove extension and common suffixes
    name = os.path.splitext(filename)[0]
    for suffix in ['个人简历', '简历', '个人', '的', '最新', '-', '_']:
        name = name.replace(suffix, ' ')
    # Try to find 2-4 Chinese character sequences
    name = name.strip()
    # Remove leading timestamp (e.g. '1778470344_')
    name = re.sub(r'^\d+[_\s]*', '', name)
    # Take first 2-4 Chinese chars as candidate name
    cn_match = re.search(r'[一-鿿]{2,4}', name)
    if cn_match:
        return cn_match.group()
    # Try 2-4 alphabetic chars
    en_match = re.search(r'[a-zA-Z]{2,20}', name)
    if en_match:
        return en_match.group()
    return name[:20] if name else ""


def process_file_task(file_path, task_type):
    try:
        # Read task metadata
        conn = get_db()
        task = conn.execute("SELECT uploaded_by, batch_name FROM task_queue WHERE file_path=?", (file_path,)).fetchone()
        conn.close()
        uploaded_by = task["uploaded_by"] if task else ""
        batch_name = task["batch_name"] if task else ""

        if task_type == "paper":
            result = process_paper(file_path)
            if not result.get("error"):
                pid = save_paper_result(file_path, result)
                # Tag paper authors with upload info
                conn = get_db()
                conn.execute("UPDATE candidates SET uploaded_by=?, batch_name=? WHERE paper_id=?", (uploaded_by, batch_name, pid))
                conn.execute("UPDATE papers SET uploaded_by=?, batch_name=? WHERE id=?", (uploaded_by, batch_name, pid))
                conn.commit()
                conn.close()
        else:
            # Extract name from filename as fallback
            filename = os.path.basename(file_path)
            fallback_name = extract_name_from_filename(filename)
            result = process_resume(file_path, fallback_name)
            # Always save — even without a name, keep the record
            conn = get_db()
            conn.execute("UPDATE candidates SET source_file=?, uploaded_by=?, batch_name=? WHERE name=? AND source='resume' AND source_file IS NULL",
                         (file_path, uploaded_by, batch_name, result.get("name", "")))
            conn.commit()
            conn.close()
        conn = get_db()
        status = "done" if not result.get("error") else "failed"
        conn.execute("UPDATE task_queue SET status=?, finished_at=datetime('now','localtime'), error_message=? WHERE file_path=?",
                     (status, result.get("error", ""), file_path))
        conn.commit()
        conn.close()
    except Exception as e:
        conn = get_db()
        conn.execute("UPDATE task_queue SET status='failed', finished_at=datetime('now','localtime'), error_message=? WHERE file_path=?",
                     (str(e), file_path))
        conn.commit()
        conn.close()

def submit_process(file_path, task_type):
    conn = get_db()
    conn.execute("UPDATE task_queue SET status='processing', started_at=datetime('now','localtime') WHERE file_path=?", (file_path,))
    conn.commit()
    conn.close()
    executor.submit(process_file_task, file_path, task_type)

@router.post("/upload")
async def upload(files: list[UploadFile] = File(...), uploader_name: str = Form(""), batch_name: str = Form(""),
                 username: str = __import__('fastapi').Depends(get_user)):
    if not uploader_name.strip():
        return {"error": "请填写上传人姓名"}
    conn = get_db()
    pending_count = conn.execute("SELECT COUNT(*) FROM task_queue WHERE status IN ('pending','processing')").fetchone()[0]
    if pending_count >= 10:
        conn.close()
        return {"error": "处理队列已满（最多10个），请等待当前任务完成"}

    results = []
    for f in files:
        if not f.filename: continue
        existing = conn.execute("SELECT status FROM task_queue WHERE file_path LIKE ? AND status IN ('pending','processing')",
                                ('%' + f.filename,)).fetchone()
        if existing:
            results.append({"file": f.filename, "status": "skipped"})
            continue

        # Save to uploader's subdirectory
        uploader = uploader_name.strip()
        uploader_dir = os.path.join(UPLOAD_DIR, uploader, batch_name.replace("/", "_") if batch_name else "_unsorted")
        os.makedirs(uploader_dir, exist_ok=True)

        ext = os.path.splitext(f.filename)[1].lower()
        safe_name = f"{int(time.time())}_{f.filename}"
        tmp_path = os.path.join(UPLOAD_DIR, safe_name)
        content = await f.read()
        with open(tmp_path, "wb") as out:
            out.write(content)

        # Auto-classify
        task_type = classify_file(tmp_path)

        # Move to correct subdirectory under uploader
        subdir = os.path.join(UPLOAD_DIR, task_type + "s", uploader, batch_name.replace("/", "_") if batch_name else "_unsorted")
        os.makedirs(subdir, exist_ok=True)
        final_path = os.path.join(subdir, safe_name)
        os.rename(tmp_path, final_path)

        conn.execute("INSERT INTO task_queue (file_path, task_type, status, uploaded_by, batch_name) VALUES (?, ?, 'pending', ?, ?)",
                     (final_path, task_type, uploader, batch_name or ""))
        results.append({"file": f.filename, "type": task_type, "status": "queued"})

    conn.commit()
    conn.close()
    return {"results": results}

@router.post("/tasks/process")
def process_pending(username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    rows = conn.execute("SELECT file_path, task_type FROM task_queue WHERE status='pending' ORDER BY created_at ASC").fetchall()
    conn.close()
    for r in rows:
        submit_process(r["file_path"], r["task_type"])
    return {"processing": len(rows)}
