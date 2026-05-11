import json
from fastapi import APIRouter, Query
from database import get_db
from api.auth import get_user

router = APIRouter(prefix="/api", tags=["papers"])

@router.get("/papers")
def list_papers(
    username: str = __import__('fastapi').Depends(get_user),
    keyword: str = Query(""),
    company: str = Query(""),
    team: str = Query(""),
    school: str = Query(""),
    is_intern: str = Query(""),  # "true" / "false"
    page: int = Query(1),
    size: int = Query(50),
):
    conn = get_db()

    # Build paper-level filters
    paper_where = ["1=1"]
    paper_params = []
    if keyword:
        paper_where.append("(p.title LIKE ? OR p.team LIKE ? OR p.raw_data LIKE ?)")
        k = f"%{keyword}%"
        paper_params.extend([k, k, k])
    if team:
        paper_where.append("p.team LIKE ?")
        paper_params.append(f"%{team}%")

    pw = " AND ".join(paper_where)
    total = conn.execute(f"SELECT COUNT(*) FROM papers p WHERE {pw}", paper_params).fetchone()[0]
    papers = conn.execute(f"SELECT p.* FROM papers p WHERE {pw} ORDER BY p.upload_time DESC LIMIT ? OFFSET ?",
                          paper_params + [size, (page - 1) * size]).fetchall()

    data = []
    for p in papers:
        raw = {}
        try: raw = json.loads(p["raw_data"]) if p["raw_data"] else {}
        except: pass

        # Get authors with optional filters
        author_where = ["paper_id=?", "source='paper'"]
        author_params = [p["id"]]
        if company:
            author_where.append("institution LIKE ?")
            author_params.append(f"%{company}%")
        if school:
            author_where.append("institution LIKE ?")
            author_params.append(f"%{school}%")
        if is_intern == "true":
            author_where.append("work_experience LIKE '%\"is_intern\": true%'")
        elif is_intern == "false":
            author_where.append("(work_experience IS NULL OR work_experience NOT LIKE '%\"is_intern\": true%')")

        aw = " AND ".join(author_where)
        authors = conn.execute(f"""SELECT id, name, email, institution, research_field,
            github_username, github_url, match_confidence, work_experience
            FROM candidates WHERE {aw}""", author_params).fetchall()
        author_list = [{"id": a["id"], "name": a["name"], "email": a["email"],
                        "institution": a["institution"], "research_field": a["research_field"],
                        "github_username": a["github_username"], "github_url": a["github_url"],
                        "match_confidence": a["match_confidence"]} for a in authors]

        task = conn.execute("SELECT t.id FROM task_queue t WHERE t.file_path = ?", (p["file_path"],)).fetchone()
        data.append({
            "id": p["id"], "title": p["title"], "file_path": p["file_path"],
            "team": p["team"], "upload_time": p["upload_time"],
            "direction": raw.get("direction", ""), "summary": raw.get("summary", ""),
            "authors": author_list, "task_id": task["id"] if task else None
        })

    conn.close()
    return {"total": total, "page": page, "data": data}


@router.get("/papers/teams")
def list_teams(username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    rows = conn.execute("SELECT team, COUNT(*) as cnt FROM papers WHERE team IS NOT NULL AND team != '' GROUP BY team ORDER BY cnt DESC").fetchall()
    conn.close()
    return {"data": [{"team": r["team"], "count": r["cnt"]} for r in rows]}


@router.get("/papers/schools")
def list_schools(username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    rows = conn.execute("SELECT institution, COUNT(*) as cnt FROM candidates WHERE source='paper' AND institution IS NOT NULL AND institution != '' GROUP BY institution ORDER BY cnt DESC").fetchall()
    conn.close()
    return {"data": [{"school": r["institution"], "count": r["cnt"]} for r in rows]}
