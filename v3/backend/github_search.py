"""GitHub API search for author profiles."""
import requests as req

def search_github_author(author):
    name = (author.get("name") or "").strip()
    email = (author.get("email") or "").strip()
    institution = (author.get("institution") or "").strip()
    if not name and not email: return None

    queries = []
    if email: queries.append(email)
    if name:
        compact = name.replace(" ", "")
        queries.append(compact)
        if " " in name: queries.append(name.replace(" ", "+"))

    seen = set()
    for q in queries:
        try:
            url = f"https://api.github.com/search/users?q={req.utils.quote(q)}&per_page=5"
            resp = req.get(url, timeout=10, headers={"Accept": "application/vnd.github.v3+json"})
            if resp.status_code != 200: continue
            for item in resp.json().get("items", []):
                login = item.get("login", "")
                if login in seen: continue
                seen.add(login)
                detail = req.get(f"https://api.github.com/users/{login}", timeout=10,
                                 headers={"Accept": "application/vnd.github.v3+json"})
                if detail.status_code != 200: continue
                u = detail.json()
                evidence = []
                if email and u.get("email", "").lower() == email.lower():
                    evidence.append("邮箱匹配")
                gh_name = (u.get("name") or "").lower().replace("-", "").replace(" ", "")
                author_name = name.lower().replace("-", "").replace(" ", "")
                if gh_name and author_name and (author_name in gh_name or gh_name in author_name):
                    evidence.append("姓名匹配")
                gh_company = (u.get("company") or "").lower()
                inst = institution.lower()
                if gh_company and inst and (inst in gh_company or gh_company in inst):
                    evidence.append("机构匹配")
                gh_loc = (u.get("location") or "").lower()
                if gh_loc and inst and (inst[:2] in gh_loc or gh_loc[:2] in inst):
                    evidence.append("地区匹配")
                confidence = "unmatched"
                if len(evidence) >= 2: confidence = "high"
                elif len(evidence) >= 1: confidence = "medium"
                if confidence != "unmatched":
                    return {"github_username": login, "github_url": u.get("html_url", f"https://github.com/{login}"), "github_match": confidence}
        except: pass
    return None
