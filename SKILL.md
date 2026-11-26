---
name: mcpsommelier
description: Find the best MCP connectors for a need (any language), preferring the ones the user already has, with cost, setup and trust warnings. Use when the user asks "which connector/MCP/integration should I use for X", "is there a connector for X", or before building an integration from scratch.
---

# MCPSommelier skill

1. Write `data/inventory.json` from the connectors you already have (name, one-line description, main tools; `"cost": true` if it spends credits).
2. Run `python3 mcpsommelier.py "<need>" --json --top 10` (add `--where cloud`, `--free` or `--blockers ...` when they apply).
3. Read `coverage` (with `substitutes` for uncovered jobs), `paid` (paid connectors, shown apart), `substitutes`, (which jobs are covered), `picks`, and for the top 3: `have`, `judge.reason`, `kind`, `setup`, `warnings`.
4. Answer in the user's language: first the connectors they already have that cover each job, then at most 2 new ones per uncovered job, each with its cost and setup.
5. Never connect, install or authorize anything without the user's OK, and never ask for keys in the chat.
