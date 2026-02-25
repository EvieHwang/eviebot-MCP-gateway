# MCP Gateway — Implementation Plan

**Date:** 2026-02-24
**Stage:** A (through Phase 1 — Discovery)
**Status:** Phase 1 ready to execute

---

## Overview

This plan is written in two stages:
- **Stage A (this document):** Phase 1 (Discovery) is fully detailed with exact commands. Phases 2-6 are outlines.
- **Stage B (post-discovery):** After Phase 1 completes, this plan is updated with discovered values and Phases 2-6 are fully detailed.

---

## Phase 1: Discovery and Validation

### 1.1 Verify Environment

Confirm we're running on Eviebot and have the expected tools.

```bash
hostname
tailscale status --self
python3 --version
node --version
aws sts get-caller-identity
```

### 1.2 Process Discovery

Find all running MCP-related processes.

```bash
ps aux | grep -i mcp
ps aux | grep -i fastmail
ps aux | grep -i music
```

### 1.3 LaunchAgent Discovery

Find launchd-managed MCP services and their configurations.

```bash
ls ~/Library/LaunchAgents/ | grep -i mcp
ls ~/Library/LaunchAgents/ | grep -i fastmail
ls ~/Library/LaunchAgents/ | grep -i music
launchctl list | grep -i mcp
launchctl list | grep -i fastmail
launchctl list | grep -i music
```

For each plist found, read it to extract:
- Working directory
- Command / program arguments
- Port bindings
- Environment variables

```bash
# Template — replace with actual plist paths found above
cat ~/Library/LaunchAgents/<plist-name>.plist
```

### 1.4 Repository Discovery

Find MCP server repos in ~/projects/.

```bash
ls ~/projects/ | grep -i mcp
ls ~/projects/ | grep -i fastmail
ls ~/projects/ | grep -i music
```

For each repo found, check:
- Framework (look for requirements.txt, package.json, pyproject.toml)
- Main entry point (app.py, main.py, server.py, index.js)
- Port configuration
- Transport type (stdio, SSE, Streamable HTTP)

### 1.5 Tailscale Discovery

Document current Tailscale Funnel/Serve configuration.

```bash
tailscale serve status
tailscale status --self
```

Record:
- Which ports are being served
- Which paths map to which local ports
- Whether Funnel is active (internet-accessible) vs Serve (tailnet-only)

### 1.6 Server Verification

Verify both servers respond to local requests.

```bash
# Check what ports are listening
lsof -iTCP -sTCP:LISTEN -P | grep -E '(python|node|uvicorn|gunicorn)'
```

For each server, attempt to list tools:
```bash
# Template — replace PORT with discovered port
curl -s http://localhost:PORT/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | python3 -m json.tool
```

If Streamable HTTP doesn't work, try SSE endpoint:
```bash
curl -s http://localhost:PORT/sse
```

### 1.7 Gateway Technology Evaluation

With discovery data in hand, evaluate the three gateway options:

| Criteria | mcp-proxy | FastMCP proxy | mcp-front |
|----------|-----------|---------------|-----------|
| Compatible with discovered transport? | | | |
| Built-in auth support? | No | No | Yes |
| Tool namespacing? | Via named servers | Via mount/proxy | Via config |
| Config-based server addition? | Yes (JSON) | Yes (Python) | Yes (YAML) |
| Language match with existing stack? | Python | Python | Go |
| Aggregates tools into single catalog? | | | |

**Decision criteria:**
1. Must work with the transport types discovered in 1.6
2. Must support tool aggregation (single catalog from multiple backends)
3. Prefer Python for consistency with existing FastMCP servers
4. Auth can be added separately — don't over-weight built-in auth

### 1.8 Document Findings

Record all discovery results. Update:
- `CLAUDE.md` — fill in discovered ports, repos, frameworks
- `docs/plan.md` — transition to Stage B with full Phase 2-6 details

---

## ⛔ STOP AFTER PHASE 1 — Update this plan before proceeding

Phase 1 discovery must complete before Phases 2-6 can be fully specified. The gateway technology choice, port numbers, transport types, and repo locations all depend on discovery results.

After Phase 1, update this plan to Stage B with:
- Discovered values filled in
- Gateway technology locked
- Phases 2-6 fully detailed with exact commands and file paths

---

## Phase 2: Gateway Setup (No Auth) — [TBD post-discovery]

**Depends on:** Phase 1 (gateway tech choice, server ports/transports)

Outline:
1. Install chosen gateway tool
2. Create gateway config with both backend servers
3. Start gateway on localhost:8080
4. Verify aggregated tool listing
5. Verify tool call routing to both backends
6. Test error handling (backend down, invalid tool name)

## Phase 3: Tailscale Reconfiguration — [TBD post-discovery]

**Depends on:** Phase 2 (working gateway), Phase 1 (current Funnel config)

Outline:
1. Remove existing Funnel/Serve configs pointing to individual servers
2. Add new Funnel config: port 443 → localhost:8080
3. Verify HTTPS access via Tailscale Funnel URL
4. Verify tool listing works over HTTPS
5. (Optional) Quick validation with claude.ai as authless connector

## Phase 4: Cognito Setup — [TBD post-discovery]

**Depends on:** Phase 3 (gateway accessible via HTTPS)

Outline:
1. Create Cognito User Pool (us-east-1 or closest region)
2. Create user (Evie) with email login
3. Create App Client with client secret, PKCE enabled
4. Request ACM certificate for auth.evehuang.com (us-east-1)
5. **Human task:** Verify ACM certificate (GitHub issue #1)
6. Configure custom domain auth.evehuang.com
7. **Human task:** Verify Route 53 DNS (GitHub issue #2)
8. Set redirect URIs: claude.ai and claude.com callbacks
9. Configure token expiry (access: 1h, refresh: 30d)

## Phase 5: Gateway Auth Integration — [TBD post-discovery]

**Depends on:** Phase 4 (Cognito ready), Phase 2 (gateway running)

Outline:
1. Add JWT validation middleware to gateway
2. Implement `.well-known/oauth-protected-resource` endpoint
3. Test with curl (obtain token manually, send as Bearer)
4. Test with MCP Inspector
5. **Human task:** Configure claude.ai connector (GitHub issue #3)
6. **Human task:** Complete OAuth login (GitHub issue #4)
7. **Human task:** Test from Claude iOS app (GitHub issue #5)

## Phase 6: Persistent Service — [TBD post-discovery]

**Depends on:** Phase 5 (auth working end-to-end)

Outline:
1. Create launchd plist for gateway
2. Load and start via launchctl
3. Verify auto-start on boot
4. Verify Tailscale Funnel persistence
5. **Human task:** Verify full flow after reboot (GitHub issue #6)
6. Document final architecture in CLAUDE.md
