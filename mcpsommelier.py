#!/usr/bin/env python3
"""MCPSommelier — the smart MCP connector finder for humans and AI agents.

Tell it what you want to do, in ANY language, and it pours you the best MCP connectors (servers) for it, ranked best
to worst: the ones you ALREADY HAVE first when they fit (zero setup), then the best new ones, with cost, setup and
trust warnings. Sibling of RepoSommelier (repos); this one is for connectors.

    python3 mcpsommelier.py "make a product video and post it to TikTok"
    python3 mcpsommelier.py "mandar facturas por correo" --inventory data/inventory.json --free
    python3 mcpsommelier.py "..." --where cloud --json                 # for agents
    python3 mcpsommelier.py --verdict io.github.owner/server good "worked great"

How it works
 1. UNDERSTANDS the need (any language): Gemini splits it into tasks and short search keywords (fallback: dictionary).
 2. LOOKS AT YOUR INVENTORY first (data/inventory.json: the connectors you already have and their tools).
 3. SEARCHES the official MCP Registry (registry.modelcontextprotocol.io) and GitHub (MCP server repos).
 4. CHECKS each candidate: hosted (remote URL) or local package (npm/pypi/docker), needs a key or login, signs of cost
    ($ per call, credits, x402 crypto payments), official vendor or community, stars, last update.
 5. JUDGE (optional, Gemini): rates 0-10 how well each fits YOUR need and profile, with a reason in your language,
    and says which task of the need each connector covers.
 6. SCORES 0-100 = relevance 35 + judge 20 + already-have 15 + trust 10 + setup 10 + freshness 5 + free 5 + verdicts.
 7. RETURNS the ranking, tiers (Use now / Add it / Look later), warnings, blocked ones with a legitimate plan B,
    and coverage: which parts of your need are covered and which still have no connector.
Read-only: it never installs, connects or authorizes anything. Never paste keys into a chat; connect them in your app.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("MCPSOMMELIER_DATA", HERE / "data"))
INDEX, CACHE = DATA / "index.json", DATA / "cache"
UA = {"User-Agent": "mcpsommelier/1.0"}
REGISTRY = "https://registry.modelcontextprotocol.io/v0/servers"
STOP = set("the a an of for to and or in on with using make create build tool tools app want need my do get "
           "de la el los las un una y o en con para por que a del al sin como hacer crear mi mis tu quiero necesito "
           "do da das dos um uma e com para fazer criar meu mcp server connector conector".split())
SYN = {"correo": ["gmail", "email"], "email": ["gmail", "email"], "video": ["video"], "imagen": ["image"], "image": ["image"],
       "tienda": ["shopify", "ecommerce"], "store": ["shopify", "ecommerce"], "diseño": ["canva", "design"], "design": ["canva", "design"],
       "voz": ["voice", "tts"], "voice": ["voice", "tts"], "calendario": ["calendar"], "calendar": ["calendar"],
       "archivos": ["drive", "files"], "files": ["drive", "files"], "notas": ["notes", "obsidian", "notion"], "notes": ["notes", "notion"],
       "redes": ["social", "tiktok", "instagram"], "social": ["social", "tiktok", "instagram"], "web": ["web", "scrape"],
       "musica": ["music"], "music": ["music"], "pagos": ["payments", "stripe"], "payments": ["payments", "stripe"]}
COST_WORDS = ("$", "per call", "credits", "x402", "paid", "subscription", "usdc", "pricing", "billing")
L = {
 "en": dict(title="Best connectors for", tiers=("Use now", "Add it", "Look later"), have="✅ you already have it",
            cols="| # | Connector | Score | Tier | Kind | Setup | What it does | Judge | Warnings |", cand="candidates",
            cov="Coverage of your need", nocov="no connector found yet", blocked="⛔ Not usable where you are TODAY",
            planb="🔁 Plan B (allowed ways only)", best="Best", besthave="Best one you already have", bestnew="Best new free one"),
 "es": dict(title="Mejores conectores para", tiers=("Usar ya", "Agregarlo", "Ver después"), have="✅ ya lo tienes",
            cols="| # | Conector | Puntos | Nivel | Tipo | Instalación | Qué hace | Juez | Avisos |", cand="candidatos",
            cov="Qué partes de tu necesidad quedan cubiertas", nocov="todavía sin conector", blocked="⛔ No sirven donde estás HOY",
            planb="🔁 Plan B (solo caminos permitidos)", best="El mejor", besthave="El mejor que ya tienes", bestnew="El mejor nuevo y gratis"),
 "pt": dict(title="Melhores conectores para", tiers=("Usar já", "Adicionar", "Ver depois"), have="✅ você já tem",
            cols="| # | Conector | Pontos | Nível | Tipo | Instalação | O que faz | Juiz | Avisos |", cand="candidatos",
            cov="Cobertura da sua necessidade", nocov="ainda sem conector", blocked="⛔ Não servem onde você está HOJE",
            planb="🔁 Plano B (só caminhos permitidos)", best="O melhor", besthave="O melhor que você já tem", bestnew="O melhor novo e grátis"),
}


def words(t):
    return [w for w in re.findall(r"[\w.+#-]{2,}", (t or "").lower()) if w not in STOP]


def load(p, d):
    try:
        return json.loads(Path(p).read_text())
    except Exception:  # noqa: BLE001
        return d


def guess_lang(text):
    t = f" {text.lower()} "
    if any(w in t for w in (" fazer ", " quero ", "ção", " não ", "ões", " com ")): return "pt"
    if any(w in t for w in (" hacer ", " quiero ", " para ", " con ", " que ", " en ", " el ", " la ", "ñ", "ción", "á", "é", "í", "ó", "ú")): return "es"
    return "en"


def _get_json(url, headers=None):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={**UA, **(headers or {})}), timeout=40) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


# ---------- Gemini (optional) ----------
def _gemini_key():
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    env = Path.home() / ".config/watch/.env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    return "proxy-injected"


def gemini_json(prompt):
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"responseMimeType": "application/json"}}).encode()
    for model in os.environ.get("MCPSOMMELIER_MODELS", "gemini-3-flash-preview,gemini-flash-latest").split(","):
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model.strip()}:generateContent",
                                     body, {**UA, "Content-Type": "application/json", "x-goog-api-key": _gemini_key()})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(json.loads(r.read())["candidates"][0]["content"]["parts"][0]["text"])
        except Exception:  # noqa: BLE001
            continue
    return None


def plan(need):
    g = gemini_json("Split this need (any language) into the separate jobs it involves and the MCP-connector search keywords for "
                    "each. Keywords: 1-2 lowercase English words, product or service names when obvious (gmail, shopify, canva, "
                    "tiktok, drive...). Return JSON {\"lang\": ISO 639-1 code of the need, \"tasks\": [{\"task\": short phrase in "
                    "the need's language, \"keywords\": [2-4 strings]}]} with 1-5 tasks. Need: " + need)
    if g and g.get("tasks"):
        return g["tasks"], g.get("lang"), "gemini"
    base = words(need)
    kws = list(dict.fromkeys([s for w in base for s in SYN.get(w, [])] + base))[:6]
    return [{"task": need, "keywords": kws}], None, "dictionary"


# ---------- sources ----------
def registry_search(keyword):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / ("reg_" + re.sub(r"[^a-z0-9]+", "_", keyword.lower())[:60] + ".json")
    if f.exists() and time.time() - f.stat().st_mtime < 86400:
        return json.loads(f.read_text())
    out, cursor = [], None
    for _ in range(3):
        url = f"{REGISTRY}?limit=100&search={urllib.parse.quote(keyword)}" + (f"&cursor={urllib.parse.quote(cursor)}" if cursor else "")
        d = _get_json(url) or {}
        for s in d.get("servers", []):
            meta = (s.get("_meta") or {}).get("io.modelcontextprotocol.registry/official", {})
            if meta.get("isLatest", True) and meta.get("status", "active") == "active":
                out.append({**s["server"], "_updated": meta.get("updatedAt", "")})
        cursor = (d.get("metadata") or {}).get("nextCursor")
        if not cursor:
            break
    f.write_text(json.dumps(out))
    return out


def github_mcp_search(keyword):
    r = subprocess.run(["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={keyword} mcp server in:name,description,topics",
                        "-f", "sort=stars", "-f", "per_page=15"], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout).get("items", []) if r.returncode == 0 else []


def days_since(iso):
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso.replace("Z", "+00:00"))).days
    except Exception:  # noqa: BLE001
        return 9999


# ---------- evaluation ----------
def describe_registry(s):
    remotes, pkgs = s.get("remotes") or [], s.get("packages") or []
    kind = "hosted" if remotes else ("local " + "/".join(sorted({p.get("registryType", "?") for p in pkgs}))) if pkgs else "unknown"
    headers = [h for r in remotes for h in (r.get("headers") or [])]
    envs = [e for p in pkgs for e in (p.get("environmentVariables") or [])]
    needs_key = any(h.get("isSecret") or "token" in (h.get("name", "") + h.get("description", "")).lower() for h in headers) \
        or any(e.get("isSecret") for e in envs)
    text = f"{s.get('title', '')} {s.get('description', '')}"
    cost = any(w in text.lower() for w in COST_WORDS)
    middleman = any("smithery" in (r.get("url") or "") for r in remotes)
    return {"kind": kind, "needs_key": needs_key, "cost": cost, "middleman": middleman, "text": text,
            "repo": (s.get("repository") or {}).get("url", ""), "updated_days": days_since(s.get("_updated", ""))}


def official_vendor(name, repo):
    """Published by the company behind the service (namespace like com.vendor / io.github.vendor) instead of a third party."""
    ns = name.split("/")[0].lower()
    owner = repo.rstrip("/").split("/")[-2].lower() if repo.count("/") >= 4 else ""
    leaf = name.split("/")[-1].lower()
    return bool(owner) and (owner in ns or owner in leaf.split("-")[0]) and not ns.startswith(("ai.smithery", "io.github.mcp"))


def relevance(text, terms):
    t = set(words(text))
    return sum(1 for x in terms if x in t or any(x in w for w in t)) / max(1, len(terms))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("need", nargs="?", help="what you want to do, in any language")
    ap.add_argument("--inventory", default=str(DATA / "inventory.json"), help="connectors you already have (see inventory.example.json)")
    ap.add_argument("--profile", default=str(DATA / "profile.json"))
    ap.add_argument("--where", help="cloud | laptop: hides local-only connectors in the cloud, etc.")
    ap.add_argument("--free", action="store_true", help="only connectors with no sign of cost")
    ap.add_argument("--blockers", nargs="+", default=[], help="paid, local, key, middleman (or your own words)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--lang")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md")
    ap.add_argument("--verdict", nargs="+", metavar=("NAME", "good|bad"))
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()
    DATA.mkdir(parents=True, exist_ok=True)
    index = load(INDEX, {"searches": [], "verdicts": {}})
    if a.verdict:
        good = (a.verdict[1] if len(a.verdict) > 1 else "good").lower() in ("good", "bueno", "bom", "👍")
        index["verdicts"][a.verdict[0]] = {"verdict": "good" if good else "bad", "shift": 8 if good else -15,
                                           "note": " ".join(a.verdict[2:]), "date": f"{datetime.now():%Y-%m-%d}"}
        INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1)); print("Saved"); return
    if a.history or not a.need:
        print(json.dumps(index, ensure_ascii=False, indent=1)); return

    inv = load(a.inventory, {"connectors": []}).get("connectors", [])
    prof = load(a.profile, {})
    blockers = set(b.lower() for b in a.blockers) | set(prof.get("blockers", []))
    if a.where == "cloud": blockers.add("local")
    tasks, glang, origin = plan(a.need)
    lang = (a.lang or glang or guess_lang(a.need))[:2].lower()
    T = L.get(lang, L["en"])
    keywords = list(dict.fromkeys(k.lower() for t in tasks for k in t.get("keywords", [])))[:10]
    terms = list(dict.fromkeys(words(a.need + " " + " ".join(keywords))))
    print(f"Tasks ({origin}): {[t['task'] for t in tasks]} · keywords: {keywords}", file=sys.stderr)

    cands = {}
    for c in inv:   # what you already have
        text = f"{c.get('name')} {c.get('description', '')} {' '.join(c.get('tools', []))}"
        cands["have:" + c["name"]] = {"name": c["name"], "title": c.get("title") or c["name"], "source": "inventory", "have": True,
                                     "kind": c.get("kind", "connected"), "needs_key": False, "cost": c.get("cost", False),
                                     "middleman": False, "text": text, "repo": c.get("repo", ""), "updated_days": 0,
                                     "vendor": c.get("official", True), "stars": 0, "url": c.get("url", "")}
    for k in keywords:
        for s in registry_search(k):
            d = describe_registry(s)
            cands.setdefault(s["name"], {"name": s["name"], "title": s.get("title") or s["name"].split("/")[-1], "source": "registry",
                                         "have": False, **d, "vendor": official_vendor(s["name"], d["repo"]), "stars": 0,
                                         "url": d["repo"] or f"https://registry.modelcontextprotocol.io/v0/servers?search={urllib.parse.quote(s['name'])}"})
        for r in github_mcp_search(k):
            n = "github:" + r["full_name"]
            if r.get("archived") or r.get("fork") or "awesome" in r["full_name"].lower() or days_since(r["pushed_at"]) > 540:
                continue
            same = next((c for c in cands.values() if c.get("repo", "").lower().endswith(r["full_name"].lower())), None)
            if same:
                same["stars"] = r["stargazers_count"]; continue
            text = f"{r['full_name']} {r.get('description') or ''} {' '.join(r.get('topics') or [])}"
            cands[n] = {"name": r["full_name"], "title": r["name"], "source": "github", "have": False, "kind": "local (repo)",
                        "needs_key": any(w in text.lower() for w in ("api key", "token", "oauth")), "cost": any(w in text.lower() for w in COST_WORDS),
                        "middleman": False, "text": text, "repo": r["html_url"], "updated_days": days_since(r["pushed_at"]),
                        "vendor": False, "stars": r["stargazers_count"], "url": r["html_url"]}
        time.sleep(1.0)

    def base_score(c):
        rel = relevance(c["text"], terms)
        trust = 1.0 if c["have"] else 0.8 if c["vendor"] else min(0.7, math.log10(c["stars"] + 1) / 4) + (0.1 if c["source"] == "registry" else 0)
        setup = 1.0 if c["have"] else 0.8 if c["kind"] == "hosted" else 0.5
        setup -= 0.2 if c["needs_key"] else 0
        fresh = max(0, 1 - c["updated_days"] / 365)
        return rel, trust, setup, fresh

    pre = sorted(cands.values(), key=lambda c: -(35 * base_score(c)[0] + (15 if c["have"] else 0) + 10 * base_score(c)[1]))[:30]
    judge = {}
    if not a.no_judge and pre:
        g = gemini_json("You choose MCP connectors for ONE person. Need: «" + a.need + "». Jobs in the need: " + json.dumps([t["task"] for t in tasks], ensure_ascii=False)
                        + (f". Profile: {json.dumps(prof, ensure_ascii=False)}" if prof else "")
                        + ". Rate 0-10 how well each connector fits THIS need (connectors they already have are marked HAVE: prefer them "
                        "when they fit). Say which job it covers. Write reasons in the language with ISO code '" + lang + "'. Return JSON "
                        "{\"connectors\": [{\"name\": exact name, \"score\": 0-10, \"job\": the job it covers or \"\", \"reason\": one short sentence}]}.\n"
                        + "\n".join(f"- {c['name']}{' (HAVE)' if c['have'] else ''}: {c['text'][:200]}" for c in pre))
        for x in (g or {}).get("connectors", []):
            if isinstance(x, dict) and x.get("name"):
                judge[x["name"]] = x

    rows, blocked = [], []
    for c in pre:
        rel, trust, setup, fresh = base_score(c)
        j = judge.get(c["name"])
        if j and float(j.get("score", 0)) <= 1 and not c["have"]:
            continue                                               # the judge says it has nothing to do with the need
        uses = [b for b, on in (("paid", c["cost"]), ("local", c["kind"].startswith("local")), ("key", c["needs_key"]),
                                ("middleman", c["middleman"])) if on and b in blockers]
        if a.free and c["cost"]:
            uses.append("paid")
        if uses and not c["have"]:
            blocked.append({**{k: c[k] for k in ("name", "title", "url")}, "uses": sorted(set(uses))}); continue
        pts = (35 * rel + 20 * ((float(j["score"]) / 10) if j else rel) + (15 if c["have"] else 0) + 10 * trust + 10 * setup
               + 5 * fresh + (0 if c["cost"] else 5) + index["verdicts"].get(c["name"], {}).get("shift", 0))
        pts = max(0, min(100, round(pts)))
        w = []
        if c["have"]: w.append(T["have"])
        if c["cost"]: w.append("💳 cost")
        if c["needs_key"]: w.append("🔑 key/login")
        if c["middleman"]: w.append("↪ via a third-party host")
        if c["vendor"] and not c["have"]: w.append("🏢 official vendor")
        if c["stars"]: w.append(f"⭐{c['stars']}")
        rows.append({"name": c["name"], "title": c["title"], "url": c["url"], "score": pts, "have": c["have"],
                     "tier": T["tiers"][0] if (c["have"] and pts >= 50) or pts >= 70 else T["tiers"][1] if pts >= 50 else T["tiers"][2],
                     "kind": c["kind"], "setup": "0" if c["have"] else ("key" if c["needs_key"] else "easy" if c["kind"] == "hosted" else "install"),
                     "what": re.sub(r"\s+", " ", c["text"])[:140], "judge": j, "warnings": w, "source": c["source"]})
    rows.sort(key=lambda x: -x["score"]); rows = rows[:a.top]
    covered = {}
    for r in rows:
        job = (r["judge"] or {}).get("job")
        if job: covered.setdefault(job, []).append(r["title"])
    coverage = [{"task": t["task"], "by": next((v for k, v in covered.items() if k and (k.lower() in t["task"].lower() or t["task"].lower() in k.lower())), [])}
                for t in tasks]
    picks = {"best": rows[0]["name"] if rows else None,
             "best_you_have": next((r["name"] for r in rows if r["have"]), None),
             "best_new_free": next((r["name"] for r in rows if not r["have"] and "💳 cost" not in r["warnings"]), None)}
    plan_b = [{"name": b["name"], "how": {"paid": "look for the vendor's free tier or a free local alternative",
                                          "local": "run it on your own computer, or pick a hosted connector for the same service",
                                          "key": "create the key in the service and connect it in your app's connector settings (never paste it in a chat)",
                                          "middleman": "prefer the vendor's official connector over a third-party host"}.get(b["uses"][0], "-")} for b in blocked[:6]]
    index["searches"].append({"date": f"{datetime.now():%Y-%m-%d %H:%M}", "need": a.need, "tasks": [t["task"] for t in tasks],
                              "top": [r["name"] for r in rows[:5]], "picks": picks})
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1))
    if a.json:
        print(json.dumps({"need": a.need, "lang": lang, "tasks": tasks, "candidates": len(cands), "picks": picks, "coverage": coverage,
                          "ranking": rows, "blocked_today": blocked, "plan_b": plan_b}, ensure_ascii=False, indent=1)); return
    out = [f"# {T['title']}: {a.need}", f"{len(cands)} {T['cand']} · {datetime.now():%Y-%m-%d}", "",
           f"**{T['best']}:** {picks['best'] or '—'} · **{T['besthave']}:** {picks['best_you_have'] or '—'} · **{T['bestnew']}:** {picks['best_new_free'] or '—'}", "",
           T["cols"], "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        jj = f"{float(r['judge']['score']):.0f}/10 {r['judge'].get('reason', '')}" if r["judge"] else ""
        name = f"[{r['title']}]({r['url']})" if r["url"] else f"**{r['title']}**"
        out.append(f"| {i} | {name} | {r['score']} | {r['tier']} | {r['kind']} | {r['setup']} | "
                   f"{r['what'].replace('|', '/')} | {jj.replace('|', '/')} | {' '.join(r['warnings'])} |")
    out += ["", f"## {T['cov']}"] + [f"- **{c['task']}** → {', '.join(c['by']) if c['by'] else T['nocov']}" for c in coverage]
    if blocked:
        out += ["", f"## {T['blocked']}"] + [f"- [{b['title']}]({b['url']}) — {', '.join(b['uses'])}" if b["url"] else f"- {b['title']} — {', '.join(b['uses'])}" for b in blocked]
        out += ["", f"## {T['planb']}"] + [f"- **{p['name']}**: {p['how']}" for p in plan_b]
    text = "\n".join(out)
    if a.md: Path(a.md).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
