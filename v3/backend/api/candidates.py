import json
from fastapi import APIRouter, Query
from database import get_db
from api.auth import get_user

router = APIRouter(prefix="/api", tags=["candidates"])

@router.get("/candidates")
def list_candidates(
    username: str = __import__('fastapi').Depends(get_user),
    keyword: str = Query(""),
    company: str = Query(""),
    degree: str = Query(""),
    page: int = Query(1),
    size: int = Query(50),
):
    conn = get_db()
    where = ["c.status='active'", "c.source='resume'"]
    params = []

    if keyword:
        where.append("(c.name LIKE ? OR c.email LIKE ? OR c.institution LIKE ? OR c.research_field LIKE ? OR c.github_username LIKE ?)")
        k = f"%{keyword}%"
        params.extend([k, k, k, k, k])
    if company:
        where.append("c.work_experience LIKE ?")
        params.append(f"%{company}%")
    if degree:
        where.append("c.degree = ?")
        params.append(degree)

    wc = " AND ".join(where)
    total = conn.execute(f"SELECT COUNT(*) FROM candidates c WHERE {wc}", params).fetchone()[0]
    rows = conn.execute(f"""
        SELECT c.* FROM candidates c WHERE {wc}
        ORDER BY c.created_at DESC LIMIT ? OFFSET ?
    """, params + [size, (page - 1) * size]).fetchall()
    conn.close()

    data = []
    for r in rows:
        d = dict(r)
        for f in ["education", "work_experience", "skills"]:
            try: d[f] = json.loads(d[f]) if d[f] else []
            except: d[f] = []
        data.append(d)
    return {"total": total, "page": page, "data": data}


@router.get("/candidates/{cid}")
def candidate_detail(cid: int, username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    row = conn.execute("SELECT * FROM candidates WHERE id=?", (cid,)).fetchone()
    conn.close()
    if not row:
        return {"error": "Not found"}
    d = dict(row)
    for f in ["education", "work_experience", "skills"]:
        try: d[f] = json.loads(d[f]) if d[f] else []
        except: d[f] = []
    return d


@router.delete("/candidates/{cid}")
def delete_candidate(cid: int, username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    conn.execute("DELETE FROM candidates WHERE id=?", (cid,))
    conn.commit()
    conn.close()
    return {"ok": True}


@router.get("/companies")
def list_companies(username: str = __import__('fastapi').Depends(get_user)):
    """Get distinct companies from work_experience JSON."""
    conn = get_db()
    rows = conn.execute("SELECT work_experience FROM candidates WHERE source='resume' AND work_experience IS NOT NULL").fetchall()
    conn.close()
    companies = {}
    for r in rows:
        try:
            exps = json.loads(r["work_experience"])
            for exp in exps:
                c = exp.get("company", "").strip()
                if c:
                    companies[c] = companies.get(c, 0) + 1
        except: pass
    return {"data": [{"company": k, "count": v} for k, v in sorted(companies.items(), key=lambda x: -x[1])]}


@router.get("/degrees")
def list_degrees(username: str = __import__('fastapi').Depends(get_user)):
    conn = get_db()
    rows = conn.execute("SELECT degree, COUNT(*) as cnt FROM candidates WHERE source='resume' AND degree IS NOT NULL AND degree != '' GROUP BY degree ORDER BY cnt DESC").fetchall()
    conn.close()
    return {"data": [{"degree": r["degree"], "count": r["cnt"]} for r in rows]}
