import hashlib, sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import ensure_tables, get_db
from config import SECRET_KEY
from api.auth import router as auth_router
from api.upload import router as upload_router, submit_process
from api.candidates import router as candidates_router
from api.papers import router as papers_router
from api.tasks import router as tasks_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ensure_tables()

    conn = get_db()
    pw = hashlib.sha256(f"admin{SECRET_KEY}".encode()).hexdigest()
    conn.execute("INSERT OR IGNORE INTO users (username, password_hash, role) VALUES ('admin', ?, 'admin')", (pw,))
    conn.commit()

    pending = conn.execute("SELECT file_path, task_type FROM task_queue WHERE status='pending'").fetchall()
    conn.close()
    if pending:
        print(f"  ⏳ 发现 {len(pending)} 个待处理任务，自动开始处理...")
        for r in pending:
            submit_process(r["file_path"], r["task_type"])

    print(f"""
╔══════════════════════════════════════════╗
║  🎯 人才数据库 v3                      ║
║  http://localhost:8081                  ║
║  账号: admin / admin                    ║
╚══════════════════════════════════════════╝
""")
    yield

app = FastAPI(title="AI Talent Database v3", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(candidates_router)
app.include_router(papers_router)
app.include_router(tasks_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
