import os, time, json
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, UploadFile, File, Form
from database import get_db
from config import UPLOAD_DIR
from classifier import classify_file
from parser import process_paper, save_paper_result, process_resume
from api.auth import get_user

router = APIRouter(prefix="/api", tags=["upload"])
executor = ThreadPoolExecutor(max_workers=2)

def process_file_task(file_path, task_type):
    try:
        if task_type == "paper":
            result = process_paper(file_path)
            if not result.get("error"):
                save_paper_result(file_path, result)
        else:
            result = process_resume(file_path)
            if result.get("name"):
                conn = get_db()
                conn.execute("UPDATE candidates SET source_file=? WHERE name=? AND source='resume' AND source_file IS NULL",
                             (file_path, result["name"]))
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
async def upload(files: list[UploadFile] = File(...), username: str = __import__('fastapi').Depends(get_user)):
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

        # Save temp file for classification
        ext = os.path.splitext(f.filename)[1].lower()
        safe_name = f"{int(time.time())}_{f.filename}"
        tmp_path = os.path.join(UPLOAD_DIR, safe_name)
        os.makedirs(os.path.dirname(tmp_path), exist_ok=True)
        content = await f.read()
        with open(tmp_path, "wb") as out:
            out.write(content)

        # Auto-classify
        task_type = classify_file(tmp_path)  # "resume" or "paper"

        # Move to correct subdirectory
        subdir = os.path.join(UPLOAD_DIR, task_type + "s")
        os.makedirs(subdir, exist_ok=True)
        final_path = os.path.join(subdir, safe_name)
        os.rename(tmp_path, final_path)

        conn.execute("INSERT INTO task_queue (file_path, task_type, status, uploaded_by) VALUES (?, ?, 'pending', ?)",
                     (final_path, task_type, username))
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
