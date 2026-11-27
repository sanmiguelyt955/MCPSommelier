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
 6. SCORES 0-100 = relevance 35 + judge 20 + already-have 15 + trust 10 + setup 10 + freshness 10 + verdicts.
    Price never changes the score (the best connector may cost $1): paid ones keep their real score and are only
    MOVED to their own section, with the price when the listing says it.
 6b. For each job with no connector, and for blocked connectors, it looks for SUBSTITUTES: GitHub repos that do the
    same job (a library, CLI or app the agent can run). Legitimate substitutes only.
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
       "scraping": ["scrape", "crawl", "scraper"], "scrape": ["scrape", "crawl"], "noticias": ["news"], "news": ["news"],
       "reddit": ["reddit"], "twitter": ["twitter", "x"], "buscar": ["search"], "search": ["search"],
       "musica": ["music"], "music": ["music"], "pagos": ["payments", "stripe"], "payments": ["payments", "stripe"]}
# Made to get past a site's protections: always set aside (never recommended), whatever the user's blockers.
BYPASS_WORDS = ("stealth", "anti-bot", "antibot", "bypass cloudflare", "bypass captcha", "captcha solv", "solve captcha",
                "waf bypass", "bypass waf", "undetect", "rotating proxies", "residential proxies", "evade detection", "cookies-from-browser")
COST_WORDS = ("$", "per call", "credits", "x402", "paid", "subscription", "usdc", "pricing", "billing")
L = {
 "en": dict(title="Best connectors for", tiers=("Use now", "Add it", "Look later"), have="✅ you already have it",
            cols="| # | Connector | Score | Tier | Kind | Setup | What it does | Judge | Warnings |", cand="candidates",
            cov="Coverage of your need", nocov="no connector found yet", blocked="⛔ Not usable where you are TODAY",
            planb="🔁 Plan B (allowed ways only)", best="Best", besthave="Best one you already have", bestnew="Best new free one",
            paid="💳 Paid (same score, listed apart so you decide if the price is worth it)", subs="🧩 Substitutes for what has no connector (repos that do the same job)",
            sub_for="substitute repo for"),
 "es": dict(title="Mejores conectores para", tiers=("Usar ya", "Agregarlo", "Ver después"), have="✅ ya lo tienes",
            cols="| # | Conector | Puntos | Nivel | Tipo | Instalación | Qué hace | Juez | Avisos |", cand="candidatos",
            cov="Qué partes de tu necesidad quedan cubiertas", nocov="todavía sin conector", blocked="⛔ No sirven donde estás HOY",
            planb="🔁 Plan B (solo caminos permitidos)", best="El mejor", besthave="El mejor que ya tienes", bestnew="El mejor nuevo y gratis",
            paid="💳 De paga (misma calificación; aparte para que tú decidas si vale el precio)", subs="🧩 Sustitutos para lo que no tiene conector (repos que hacen lo mismo)",
            sub_for="repo sustituto para"),
 "pt": dict(title="Melhores conectores para", tiers=("Usar já", "Adicionar", "Ver depois"), have="✅ você já tem",
            cols="| # | Conector | Pontos | Nível | Tipo | Instalação | O que faz | Juiz | Avisos |", cand="candidatos",
            cov="Cobertura da sua necessidade", nocov="ainda sem conector", blocked="⛔ Não servem onde você está HOJE",
            planb="🔁 Plano B (só caminhos permitidos)", best="O melhor", besthave="O melhor que você já tem", bestnew="O melhor novo e grátis",
            paid="💳 Pagos (mesma nota; à parte para você decidir se vale o preço)", subs="🧩 Substitutos para o que não tem conector (repos que fazem o mesmo)",
            sub_for="repo substituto para"),
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
                    "the need's language, \"keywords\": [2-4 strings], \"ai_can_do\": true if an AI assistant does this job by itself with no "
                    "external service (summarize, write, translate, decide, plan, explain)}]} with 1-5 tasks. Need: " + need)
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


BLOCKER_WORDS = {"yt-dlp": ("yt-dlp", "youtube-dl", "yt_dlp", "downloader", "download videos"), "gpu": ("cuda", "requires a gpu"),
                 "local": (), "key": (), "middleman": ()}
AVOID = ()


def substitute_repos(keywords, exclude=(), n=3, must=()):
    """GitHub repos that do the same JOB without being a connector (a library, CLI or app the agent can run).
    Legitimate substitutes only: never tools made to get around a service's rules."""
    seen, out = set(exclude), []
    for k in keywords[:3]:
        r = subprocess.run(["gh", "api", "-X", "GET", "search/repositories", "-f", f"q={k} in:name,description,topics stars:>20",
                            "-f", "sort=stars", "-f", "per_page=10"], capture_output=True, text=True, timeout=60)
        for x in (json.loads(r.stdout).get("items", []) if r.returncode == 0 else []):
            n_ = x["full_name"]
            if n_ in seen or x.get("archived") or x.get("fork") or "awesome" in n_.lower() or days_since(x["pushed_at"]) > 540:
                continue
            hay = (n_ + " " + (x.get("description") or "") + " " + " ".join(x.get("topics") or [])).lower()
            if any(w in hay for w in AVOID) or any(w in hay for w in BYPASS_WORDS):
                continue                                       # would need something blocked here, or evades protections
            core = (n_ + " " + " ".join(x.get("topics") or [])).lower()
            if must and (sum(1 for m in set(must) if m in hay) < min(2, len(set(must))) or not any(m in core for m in must)):
                continue                                       # a substitute must be about the same job
            seen.add(n_)
            lic = ((x.get("license") or {}).get("spdx_id") or "none").lower()
            out.append({"repo": n_, "url": x["html_url"], "stars": x["stargazers_count"], "license": lic,
                        "description": (x.get("description") or "")[:120]})
        time.sleep(1.0)
        if len(out) >= n:
            break
    return sorted(out, key=lambda x: -x["stars"])[:n]


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
            "repo": (s.get("repository") or {}).get("url", ""), "updated_days": days_since(s.get("_updated", "")),
            "endpoint": next((r.get("url") for r in remotes if r.get("url")), ""),
            "packages": [{"type": p.get("registryType"), "id": p.get("identifier")} for p in pkgs if p.get("identifier")]}


PRICE_RE = re.compile(r"(\$\s?\d+(?:[.,]\d+)?(?:\s?(?:/|per)\s?(?:call|request|month|mo|image|video|minute|min|1k|1000)\w*)?)", re.I)


def price_of(text):
    m = PRICE_RE.search(text or "")
    return m.group(1).replace(" ", "") if m else None


def official_vendor(name, repo):
    """Published by the company behind the service (namespace like com.vendor / io.github.vendor) instead of a third party."""
    ns = name.split("/")[0].lower()
    owner = repo.rstrip("/").split("/")[-2].lower() if repo.count("/") >= 4 else ""
    leaf = name.split("/")[-1].lower()
    return bool(owner) and (owner in ns or owner in leaf.split("-")[0]) and not ns.startswith(("ai.smithery", "io.github.mcp"))


def relevance(text, terms):
    t = set(words(text))
    stem = lambda w: w[:5] if len(w) >= 5 else w  # noqa: E731   (scraping ~ scrape ~ scraper)
    st = {stem(w) for w in t}
    return sum(1 for x in terms if x in t or stem(x) in st or any(x in w for w in t)) / max(1, len(terms))



SKILLSOMMELIER = Path(__file__).resolve().parent.parent / "skillsommelier" / "skillsommelier.py"

def substitute_skills(task, top=3):
    """Agent Skills for a job with no connector (SkillSommelier, when it sits next to this repo)."""
    if not SKILLSOMMELIER.exists():
        return []
    try:
        r = subprocess.run([sys.executable, str(SKILLSOMMELIER), task, "--json", "--no-family", "--no-judge", "--top", str(top)],
                           capture_output=True, text=True, timeout=600)
        return [f"{x['repo']}/{x['skill']}" for x in json.loads(r.stdout).get("results", [])[:top]]
    except Exception:  # noqa: BLE001
        return []

FAIR = False   # --fair: the connectors you have get no bonus (they only keep the ✅ mark)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("need", nargs="?", help="what you want to do, in any language")
    ap.add_argument("--inventory", default=str(DATA / "inventory.json"), help="connectors you already have (see inventory.example.json)")
    ap.add_argument("--profile", default=str(DATA / "profile.json"))
    ap.add_argument("--where", help="cloud | laptop: hides local-only connectors in the cloud, etc.")
    ap.add_argument("--free", action="store_true", help="kept for compatibility: paid connectors always go to their own section (-10 points)")
    ap.add_argument("--blockers", nargs="+", default=[], help="paid, local, key, middleman (or your own words)")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--lang")
    ap.add_argument("--no-judge", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md")
    ap.add_argument("--verdict", nargs="+", metavar=("NAME", "good|bad"))
    ap.add_argument("--history", action="store_true")
    ap.add_argument("--fair", action="store_true", help="no bonus for connectors you already have: the best one wins, yours only keep the ✅ mark")
    a = ap.parse_args()
    global FAIR
    FAIR = a.fair
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
    if a.where == "cloud": blockers |= {"local", "yt-dlp"}
    global AVOID
    AVOID = tuple(w for b in blockers for w in BLOCKER_WORDS.get(b, ()))
    tasks, glang, origin = plan(a.need)
    lang = (a.lang or glang or guess_lang(a.need))[:2].lower()
    T = L.get(lang, L["en"])
    keywords = list(dict.fromkeys(k.lower() for t in tasks if not t.get("ai_can_do") for k in t.get("keywords", [])))[:10] \
        or list(dict.fromkeys(k.lower() for t in tasks for k in t.get("keywords", [])))[:10]
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
        mine = c["have"] and not FAIR
        trust = 1.0 if mine else 0.8 if c["vendor"] else min(0.7, math.log10(c["stars"] + 1) / 4) + (0.1 if c["source"] == "registry" else 0)
        setup = 1.0 if mine else 0.8 if c["kind"] in ("hosted", "connected") else 0.5
        setup -= 0.2 if c["needs_key"] else 0
        fresh = max(0, 1 - c["updated_days"] / 365)
        return rel, trust, setup, fresh

    pre = sorted(cands.values(), key=lambda c: -(35 * base_score(c)[0] + (15 if c["have"] and not FAIR else 0) + 10 * base_score(c)[1]))[:30]
    judge = {}
    if not a.no_judge and pre:
        g = gemini_json("You choose MCP connectors for ONE person. Need: «" + a.need + "». Jobs in the need: " + json.dumps([t["task"] for t in tasks], ensure_ascii=False)
                        + (f". Profile: {json.dumps(prof, ensure_ascii=False)}" if prof else "")
                        + ". Rate 0-10 how well each connector fits THIS need (connectors they already have are marked HAVE: prefer them "
                        "when they fit). Say which job it covers. Write reasons in the language with ISO code '" + lang + "'. Return JSON "
                        "{\"connectors\": [{\"name\": exact name, \"score\": 0-10, \"job\": the job it covers or \"\", \"reason\": one short sentence}]}.\n"
                        + "\n".join(f"- {c['name']}{' (HAVE)' if c['have'] else ''}: {c['text'][:200]}" for c in pre))
        names = {c["name"].lower(): c["name"] for c in pre}
        for x in (g or {}).get("connectors", []):
            if isinstance(x, dict) and x.get("name"):
                key = re.sub(r"\s*\(have\)\s*$", "", x["name"].strip(), flags=re.I).lower()
                if key in names:
                    judge[names[key]] = x

    rows, blocked = [], []
    for c in pre:
        rel, trust, setup, fresh = base_score(c)
        j = judge.get(c["name"])
        if judge:
            if (j and float(j.get("score", 0)) < 4) or (not j and rel < 0.25):
                continue                                           # the judge says (or relevance shows) it does not fit
        elif rel < 0.2:
            continue                                               # no judge today: relevance alone decides what fits
        uses = [b for b, on in (("local", c["kind"].startswith("local")), ("key", c["needs_key"]),
                                ("middleman", c["middleman"])) if on and b in blockers]
        if any(w in c["text"].lower() for w in BYPASS_WORDS) and not c["have"]:
            uses.append("bypass")
        if uses and not c["have"]:
            bp = (35 * rel + 20 * ((float(j["score"]) / 10) if j else rel) + 10 * trust + 10 * setup + 10 * fresh)
            blocked.append({**{k: c[k] for k in ("name", "title", "url")}, "uses": sorted(set(uses)), "score": max(0, min(100, round(bp)))}); continue
        pts = (35 * rel + 20 * ((float(j["score"]) / 10) if j else rel) + (15 if c["have"] and not FAIR else 0) + 10 * trust + 10 * setup
               + 10 * fresh + index["verdicts"].get(c["name"], {}).get("shift", 0))
        pts = max(0, min(100, round(pts)))
        w = []
        if c["have"]: w.append(T["have"])
        if c["cost"]:
            pr = price_of(c["text"]); w.append(f"💳 {pr}" if pr else "💳 cost")
        if c["needs_key"]: w.append("🔑 key/login")
        if c["middleman"]: w.append("↪ via a third-party host")
        if c["vendor"] and not c["have"]: w.append("🏢 official vendor")
        if c["stars"]: w.append(f"⭐{c['stars']}")
        rows.append({"name": c["name"], "title": c["title"], "url": c["url"], "score": pts, "have": c["have"],
                     "tier": T["tiers"][0] if (c["have"] and pts >= 50) or pts >= 70 else T["tiers"][1] if pts >= 50 else T["tiers"][2],
                     "kind": c["kind"], "setup": "0" if c["have"] else ("key" if c["needs_key"] else "easy" if c["kind"] == "hosted" else "install"),
                     "what": re.sub(r"\s+", " ", c["text"])[:140], "judge": j, "warnings": w, "source": c["source"], "paid": c["cost"],
                     "endpoint": c.get("endpoint", ""), "packages": c.get("packages", []), "repo_url": c.get("repo", "")})
    rows.sort(key=lambda x: -x["score"])
    paid_rows = [r for r in rows if r["paid"]][:a.top]
    rows = [r for r in rows if not r["paid"]][:a.top]
    covered = {}
    for r in rows + paid_rows:
        job = (r["judge"] or {}).get("job")
        if job and float((r["judge"] or {}).get("score", 0)) >= 6:      # only a real fit covers a job
            covered.setdefault(job, []).append(r["title"])
    if not judge and len(tasks) == 1:
        covered.setdefault(tasks[0]["task"], []).extend(r["title"] for r in rows + paid_rows
                                                       if relevance(r["what"], terms) >= (0.3 if T["have"] in r["warnings"] else 0.4))
    coverage = [{"task": t["task"], "by": next((v for k, v in covered.items() if k and (k.lower() in t["task"].lower() or t["task"].lower() in k.lower())), [])}
                for t in tasks]
    subs = []
    for c, t in zip(coverage, tasks):
        if t.get("ai_can_do"):
            c["ai"] = True
            if "_need_skills" not in locals():
                _need_skills = substitute_skills(a.need)      # a skill teaches the AI to do it better (one search per need)
            c["skills"] = _need_skills
            continue
        if not c["by"]:
            kw = t.get("keywords", []) or words(t["task"])
            found = substitute_repos(kw, must=[w for k in kw for w in words(k) if len(w) >= 4])
            subs.append({"task": t["task"], "repos": found})
            c["substitutes"] = [x["repo"] for x in found]
            c["skills"] = substitute_skills(t["task"])        # connector → repo AND skill (SkillSommelier)
    picks = {"best": rows[0]["name"] if rows else None,
             "best_you_have": next((r["name"] for r in rows if r["have"]), None),
             "best_new_free": next((r["name"] for r in rows if not r["have"] and not r["paid"]), None),
             "best_paid": paid_rows[0]["name"] if paid_rows else None}
    HOW = {"en": {"paid": "look for the vendor's free tier or a free local alternative",
                  "local": "run it on your own computer, or pick a hosted connector for the same service",
                  "key": "create the key in the service and connect it in your app's connector settings (never paste it in a chat)",
                  "middleman": "prefer the vendor's official connector over a third-party host",
                  "bypass": "not recommended: it is made to get past sites' protections; use official APIs or the site's allowed data"},
           "es": {"paid": "busca la capa gratis del servicio o una alternativa local gratis",
                  "local": "córrelo en tu computadora, o elige un conector alojado para el mismo servicio",
                  "key": "crea la clave en el servicio y conéctala en los ajustes de conectores de tu app (nunca la pegues en un chat)",
                  "middleman": "prefiere el conector oficial del servicio en vez de uno alojado por terceros",
                  "bypass": "no recomendado: está hecho para saltarse las protecciones de los sitios; usa APIs oficiales o los datos que el sitio permite"},
           "pt": {"paid": "procure o plano grátis do serviço ou uma alternativa local grátis",
                  "local": "rode no seu computador, ou escolha um conector hospedado para o mesmo serviço",
                  "key": "crie a chave no serviço e conecte nas configurações de conectores do seu app (nunca cole em um chat)",
                  "middleman": "prefira o conector oficial do serviço em vez de um hospedado por terceiros",
                  "bypass": "não recomendado: feito para burlar as proteções dos sites; use APIs oficiais"}}
    plan_b = []
    task_kw = [w for k in keywords for w in words(k) if len(w) >= 4]
    for b in sorted(blocked, key=lambda x: -x["score"])[:5]:
        kw = [w for w in words(b["title"]) if w not in ("mcp", "server", "agent", "claude")][:2]
        first = "bypass" if "bypass" in b["uses"] else b["uses"][0]
        plan_b.append({"name": b["name"], "how": HOW.get(lang, HOW["en"]).get(first, "-"),
                       "substitutes": substitute_repos([" ".join(kw)], exclude=(b["name"],), n=2, must=task_kw) if kw else []})
    index["searches"].append({"date": f"{datetime.now():%Y-%m-%d %H:%M}", "need": a.need, "tasks": [t["task"] for t in tasks],
                              "top": [r["name"] for r in rows[:5]], "picks": picks})
    INDEX.write_text(json.dumps(index, ensure_ascii=False, indent=1))
    if a.json:
        print(json.dumps({"need": a.need, "lang": lang, "tasks": tasks, "candidates": len(cands), "picks": picks, "coverage": coverage,
                          "ranking": rows, "paid": paid_rows, "substitutes": subs,
                          "blocked_today": blocked, "plan_b": plan_b}, ensure_ascii=False, indent=1)); return
    out = [f"# {T['title']}: {a.need}", f"{len(cands)} {T['cand']} · {datetime.now():%Y-%m-%d}", "",
           f"**{T['best']}:** {picks['best'] or '—'} · **{T['besthave']}:** {picks['best_you_have'] or '—'} · **{T['bestnew']}:** {picks['best_new_free'] or '—'}", "",
           T["cols"], "|---|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        jj = f"{float(r['judge']['score']):.0f}/10 {r['judge'].get('reason', '')}" if r["judge"] else ""
        name = f"[{r['title']}]({r['url']})" if r["url"] else f"**{r['title']}**"
        out.append(f"| {i} | {name} | {r['score']} | {r['tier']} | {r['kind']} | {r['setup']} | "
                   f"{r['what'].replace('|', '/')} | {jj.replace('|', '/')} | {' '.join(r['warnings'])} |")
    if paid_rows:
        out += ["", f"## {T['paid']}", T["cols"], "|---|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(paid_rows, 1):
            name = f"[{r['title']}]({r['url']})" if r["url"] else f"**{r['title']}**"
            jj = f"{float(r['judge']['score']):.0f}/10 {r['judge'].get('reason', '')}" if r["judge"] else ""
            out.append(f"| {i} | {name} | {r['score']} | {r['tier']} | {r['kind']} | {r['setup']} | "
                       f"{r['what'].replace('|', '/')} | {jj.replace('|', '/')} | {' '.join(r['warnings'])} |")
    out += ["", f"## {T['cov']}"] + [f"- **{c['task']}** → {('🤖 ' + {'es': 'lo hace la IA, no necesita conector', 'pt': 'a IA faz isso, não precisa de conector'}.get(lang, 'the AI does this itself, no connector needed') + (' · 🎓 ' + ', '.join(c.get('skills', [])) if c.get('skills') else '')) if c.get('ai') else ', '.join(c['by']) if c['by'] else T['nocov'] + (' · 🧩 ' + ', '.join(c.get('substitutes', [])) if c.get('substitutes') else '') + (' · 🎓 ' + ', '.join(c.get('skills', [])) if c.get('skills') else '')}" for c in coverage]
    if subs:
        out += ["", f"## {T['subs']}"]
        for sb in subs:
            out += [f"- **{sb['task']}** → [{x['repo']}]({x['url']}) ({x['stars']}⭐, {x['license']}) — {x['description'].replace('|', '/')}" for x in sb["repos"]] or [f"- **{sb['task']}** → —"]
    if blocked:
        out += ["", f"## {T['blocked']}"] + [f"- [{b['title']}]({b['url']}) ({b['score']}) — {', '.join(b['uses'])}" if b["url"] else f"- {b['title']} ({b['score']}) — {', '.join(b['uses'])}" for b in sorted(blocked, key=lambda x: -x['score'])]
        out += ["", f"## {T['planb']}"]
        for pb in plan_b:
            alt = "; ".join(f"[{x['repo']}]({x['url']}) ({x['stars']}⭐)" for x in pb["substitutes"])
            out.append(f"- **{pb['name']}**: {pb['how']}" + (f" · 🧩 {T['sub_for']}: {alt}" if alt else ""))
    text = "\n".join(out)
    if a.md: Path(a.md).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
