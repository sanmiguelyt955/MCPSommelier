# 🍷🔌 MCPSommelier

**The smart MCP connector finder for humans and AI agents.** Tell it what you want to do — in **any language** — and it pours you the **best connectors (MCP servers) for it**, ranked best to worst. The ones you **already have** come first when they fit (zero setup); then the best new ones, with cost, setup and trust warnings.

Sibling of [RepoSommelier](https://github.com/sanmiguelyt955/RepoSommelier) (that one finds repos; this one finds connectors). [Leer en español](README.es.md)

```bash
python3 mcpsommelier.py "make a product video and post it to TikTok"
python3 mcpsommelier.py "mandar facturas por correo" --free
python3 mcpsommelier.py "..." --where cloud --json        # for agents
python3 mcpsommelier.py --verdict io.github.owner/server good "worked great"
```

## What makes it different
| | Browsing a directory | Asking an LLM | **MCPSommelier** |
|---|---|---|---|
| Live catalog (official MCP Registry + GitHub) | ✅ | ❌ | ✅ |
| Understands a need in any language and splits it into jobs | ❌ | ✅ | ✅ |
| Prefers the connectors **you already have** | ❌ | ❌ | ✅ (`inventory.json`) |
| Hosted vs local, key/login needed, signs of cost, official vendor vs third-party copy | partly | rarely | ✅ |
| **Coverage**: which parts of your need are covered, which still have no connector | ❌ | ❌ | ✅ |
| Blocked ones set aside with a legitimate plan B | ❌ | ❌ | ✅ |
| Learns from your verdicts · JSON for agents | ❌ | ❌ | ✅ |

## How it works
1. **Understands** the need and splits it into jobs with short search keywords (Gemini; dictionary fallback).
2. **Your inventory first**: `data/inventory.json` lists the connectors you already have and their tools (an agent can write it from its own tool list).
3. **Searches** the official [MCP Registry](https://registry.modelcontextprotocol.io) and GitHub.
4. **Checks** each one: hosted (remote URL) or local package, key/login needed, signs of cost ($ per call, credits, x402), official vendor or community, stars, last update.
5. **Judge** (optional, Gemini): 0-10 fit for your need and profile, which job it covers, and a reason in your language.
6. **Scores** 0-100 = relevance 35 + judge 20 + already-have 15 + trust 10 + setup 10 + freshness 10 + your verdicts. Price never changes the score.
7. **Returns** tiers (**Use now** · **Add it** · **Look later**), warnings (✅ you have it, 💳 cost, 🔑 key/login, ↪ third-party host, 🏢 official vendor), coverage of your need, and blocked ones with a plan B.

## Paid connectors and substitutes
- **Price never lowers a score**: the best connector on the market may cost $1. Paid ones keep their real score and are only **moved** to their own section, *"💳 Paid"*, with the price when the listing says it, so you decide.
- **Coverage**: a job counts as covered only when the judge rates a connector 6/10 or more for it.
- **Substitutes**: for every job with no connector (and for blocked connectors), it looks for **GitHub repos that do the
  same job** — a library, CLI or app the agent can run. Legitimate substitutes only; check each one's license and the
  service's terms (for example, some unofficial chat libraries break the service's rules: prefer official APIs).

## Blockers and plan B
`--where cloud` sets aside local-only connectors; `--blockers local key middleman` sets aside others. Paid ones always go to their own section.
Blocked connectors are never deleted: they go to their own list with a legitimate plan B (free tier, hosted alternative, the vendor's official connector...). It never suggests ways around a service's rules.

## Setup
Python 3.9+ (standard library only) and `gh` logged in (GitHub search). Optional: `GEMINI_API_KEY` (free from Google AI Studio).
Copy `data/inventory.example.json` → `data/inventory.json` and `data/profile.example.json` → `data/profile.json`.

## Safety
Read-only: it never installs, connects or authorizes a connector. Connect keys in your app's connector settings, never in a chat. A high score is not a security review.

## License
MIT © 2026 sanmiguelyt955
