import os
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from database import get_db
from api.auth import get_user, _get_session
from urllib.parse import quote

router = APIRouter(prefix="/api", tags=["tasks"])

@router.get("/tasks")
def list_tasks(username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    rows = conn.execute("SELECT * FROM task_queue ORDER BY created_at DESC LIMIT 50").fetchall()
    conn.close()
    return {"data": [dict(r) for r in rows]}

@router.delete("/tasks/{tid}")
def delete_task(tid: int, authorization: str = Header(None)):
    s = _get_session(authorization)
    conn = get_db()
    row = conn.execute("SELECT file_path, task_type, uploaded_by FROM task_queue WHERE id=?", (tid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "任务不存在")
    if s["role"] != "admin" and row["uploaded_by"] != s["username"]:
        conn.close()
        raise HTTPException(403, "只能删除自己上传的文件")
    fp, ft = row["file_path"], row["task_type"]
    if os.path.exists(fp):
        os.remove(fp)
    conn.execute("DELETE FROM candidates WHERE source=? AND source_file=?", (ft, fp))
    conn.execute("DELETE FROM task_queue WHERE id=?", (tid,))
    conn.execute("DELETE FROM papers WHERE file_path=?", (fp,))
    conn.commit()
    conn.close()
    return {"ok": True}

@router.get("/download/{tid}")
def download_file(tid: int):
    conn = get_db()
    row = conn.execute("SELECT file_path FROM task_queue WHERE id=?", (tid,)).fetchone()
    conn.close()
    if not row or not os.path.exists(row["file_path"]):
        return {"error": "文件不存在"}
    fp = row["file_path"]
    return FileResponse(fp, filename=os.path.basename(fp))
