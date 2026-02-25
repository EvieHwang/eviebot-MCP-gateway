# MCP Gateway — Implementation Plan

**Date:** 2026-02-24
**Stage:** B (post-discovery, all phases detailed)
**Status:** Phase 1 complete. Ready for Phase 2.

---

## Discovery Results (Phase 1 — Completed)

### Servers Found

| Server | Port | Bind | Repo | Framework | Transport | LaunchAgent |
|--------|------|------|------|-----------|-----------|-------------|
| Fastmail | 8000 | localhost | ~/projects/fastmail-mcp-server | FastMCP 3.0.2 (Python) | Streamable HTTP `/mcp` | com.evie.fastmail-mcp |
| Music | 3000 | *:3000 | ~/projects/mood-playlist-mcp | @modelcontextprotocol/sdk 1.27 (Node/TS) | Streamable HTTP `/mcp` | com.mood-playlist-mcp |

### Tailscale Funnel (current)

```
https://eviebot.tailf90db7.ts.net       → http://127.0.0.1:8000 (Fastmail)
https://eviebot.tailf90db7.ts.net:8443  → http://127.0.0.1:3000 (Music)
```

Both Funnel endpoints are active (internet-accessible).

### Auth (existing)

Both servers already implement full OAuth 2.1 with the same Cognito User Pool:
- **User Pool:** `us-east-1_4Y1JyaYkC`
- **Public Client ID:** `2m0mavh487mal44dgrd9vkr07a`
- **Issuer:** `https://cognito-idp.us-east-1.amazonaws.com/us-east-1_4Y1JyaYkC`
- Fastmail: `CognitoAuthProvider` in `auth.py` (proxies Cognito metadata, DCR, JWT validation)
- Music: `MoodPlaylistOAuthProvider` in `src/auth/oauth-provider.ts`

Both servers return 401 without a valid Bearer token. Both serve `/.well-known/oauth-protected-resource`.

### Key Discovery Insight

Since both servers already have Cognito OAuth, the gateway has two auth strategies:
1. **Gateway-level auth only:** Gateway validates JWT, forwards to backends without auth (backends need localhost-only mode or a bypass)
2. **Pass-through auth:** Gateway validates JWT, then passes the same Bearer token to backends (they already accept it)

Option 2 is simpler since it requires **no changes** to existing servers. The gateway just proxies requests including the Authorization header.

### Gateway Technology Evaluation

| Criteria | mcp-proxy | FastMCP proxy | mcp-front |
|----------|-----------|---------------|-----------|
| Compatible with Streamable HTTP? | Yes | Yes | Yes |
| Built-in auth support? | No | Via RemoteAuthProvider | Yes (built-in) |
| Tool namespacing? | Named servers with paths | `mount()` method | Config-based |
| Config-based server addition? | JSON config | Python code | YAML config |
| Language match? | Python | Python | Go |
| Aggregates into single catalog? | No (separate paths per server) | Yes (`mount` merges tools) | Yes |
| Pass-through Bearer tokens? | Yes (proxy) | Needs custom code | Yes |

**Decision: FastMCP proxy mode** is the best fit because:
1. Fastmail server already uses FastMCP — we know the framework works
2. `mount()` merges tools from multiple servers into a single catalog (exactly what we need)
3. Python is consistent with the existing stack
4. We can reuse the existing `CognitoAuthProvider` auth pattern from fastmail-mcp-server
5. No external binary to install — just `pip install fastmcp`

---

## Phase 2: Gateway Setup (No Auth)

**Goal:** Get a working gateway that aggregates tools from both servers on localhost:8080.

### 2.1 Create Project Structure

```bash
cd ~/projects/eviebot-MCP-gateway
python -m venv .venv
# Activate via direnv (.envrc)
pip install fastmcp
pip freeze > requirements.txt
```

### 2.2 Create Gateway Server

Create `gateway.py` using FastMCP's proxy/mount pattern:

```python
from fastmcp import FastMCP

gateway = FastMCP("eviebot-gateway")

# Mount backend servers by their Streamable HTTP URLs
# FastMCP's mount() connects to remote servers and merges their tools
gateway.mount("fastmail", "http://localhost:8000/mcp")
gateway.mount("music", "http://localhost:3000/mcp")
```

**Key questions to resolve during implementation:**
- Does `mount()` work with Streamable HTTP transport? (Verify with FastMCP 3.x docs)
- How does `mount()` handle auth on the backend? (Backends require Bearer tokens — may need to pass through or disable backend auth for localhost)
- Does `mount()` automatically prefix tool names with the mount name?

### 2.3 Test Without Auth

Start gateway without auth first to verify aggregation works:

```bash
# Start gateway
python gateway.py  # or: fastmcp run gateway.py --port 8080

# Test tool listing
curl -s http://localhost:8080/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

Expected: Tool list includes both Fastmail tools (prefixed `fastmail_*`) and Music tools (prefixed `music_*`).

### 2.4 Handle Backend Auth

Since backends require Bearer tokens, we need a strategy for gateway→backend auth:
- **Option A:** Pass through the client's Bearer token to backends (simplest, no backend changes)
- **Option B:** Use a service-to-service token (more complex, needs new Cognito client)
- **Option C:** Add a localhost bypass to backends (requires modifying existing servers — violates constraints)

**Prefer Option A** — pass through the Bearer token.

### 2.5 Test Tool Calls

Test a tool call routes correctly:

```bash
# Test a Fastmail tool
curl -s http://localhost:8080/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "fastmail_list_mailboxes", "arguments": {}}}'
```

---

## Phase 3: Tailscale Reconfiguration

**Goal:** Point Funnel to the gateway instead of individual servers.

### 3.1 Remove Old Funnel Configs

```bash
# Remove current Funnel configs
tailscale serve --remove / --https=443
tailscale serve --remove / --https=8443
```

### 3.2 Add Gateway Funnel

```bash
# Point Funnel to gateway
tailscale serve --bg --https=443 http://localhost:8080
tailscale funnel --bg --https=443 on
```

### 3.3 Verify

```bash
tailscale serve status
# Should show: https://eviebot.tailf90db7.ts.net → http://127.0.0.1:8080

# Test externally
curl -s https://eviebot.tailf90db7.ts.net/mcp -X POST \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

---

## Phase 4: Cognito Setup

**Goal:** Ensure Cognito is properly configured for the gateway.

### 4.1 Evaluate Existing Cognito Setup

The existing User Pool (`us-east-1_4Y1JyaYkC`) and App Client are already configured and working with both servers. Check if we can reuse them as-is for the gateway.

```bash
# Check existing User Pool config
aws cognito-idp describe-user-pool --user-pool-id us-east-1_4Y1JyaYkC --region us-east-1

# Check existing App Client
aws cognito-idp describe-user-pool-client \
  --user-pool-id us-east-1_4Y1JyaYkC \
  --client-id 2m0mavh487mal44dgrd9vkr07a \
  --region us-east-1
```

### 4.2 Check Custom Domain

```bash
aws cognito-idp describe-user-pool-domain \
  --domain auth.evehwang.com \
  --region us-east-1
```

If custom domain exists and is active, Phase 4 may already be complete. If not:

### 4.3 Create Custom Domain (if needed)

1. Request ACM certificate for auth.evehwang.com in us-east-1
2. **Human task:** Verify ACM certificate (GitHub issue #1)
3. Create custom domain on Cognito User Pool
4. Create Route 53 A record alias to CloudFront distribution
5. **Human task:** Verify Route 53 DNS (GitHub issue #2)

### 4.4 Verify Callback URIs

Ensure the App Client allows these redirect URIs:
- `https://claude.ai/api/mcp/auth_callback`
- `https://claude.com/api/mcp/auth_callback`

```bash
aws cognito-idp describe-user-pool-client \
  --user-pool-id us-east-1_4Y1JyaYkC \
  --client-id 2m0mavh487mal44dgrd9vkr07a \
  --region us-east-1 \
  --query 'UserPoolClient.CallbackURLs'
```

---

## Phase 5: Gateway Auth Integration

**Goal:** Add OAuth 2.1 to the gateway so it's the single auth point.

### 5.1 Add Auth to Gateway

Reuse the `CognitoAuthProvider` pattern from fastmail-mcp-server:
- Serve `/.well-known/oauth-protected-resource` pointing to the gateway's own URL as auth server
- Proxy Cognito OIDC metadata as OAuth AS metadata (RFC 8414)
- DCR endpoint returning pre-registered Client ID
- JWT validation via Cognito JWKS

### 5.2 Update Protected Resource Metadata

The gateway's `/.well-known/oauth-protected-resource` must point to itself as the auth server (same pattern as the Fastmail server but with the gateway URL).

### 5.3 Test With curl

```bash
# Get a token (manually via Cognito hosted UI or existing session)
# Then test:
curl -s https://eviebot.tailf90db7.ts.net/mcp -X POST \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}'
```

### 5.4 Human Tasks

5. **Human task:** Configure claude.ai connector (GitHub issue #3)
   - Remove old Fastmail and Music connectors
   - Add single gateway connector URL
   - Enter Client ID/Secret in Advanced Settings
6. **Human task:** Complete OAuth login (GitHub issue #4)
7. **Human task:** Test from Claude iOS app (GitHub issue #5)

---

## Phase 6: Persistent Service

**Goal:** Gateway survives reboots.

### 6.1 Create launchd Plist

Create `~/Library/LaunchAgents/com.evie.mcp-gateway.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.evie.mcp-gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/evehwang/projects/eviebot-MCP-gateway/.venv/bin/python3</string>
        <string>gateway.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/evehwang/projects/eviebot-MCP-gateway</string>
    <key>EnvironmentVariables</key>
    <dict>
        <!-- Cognito config — same as existing servers -->
        <key>COGNITO_ISSUER_URL</key>
        <string>https://cognito-idp.us-east-1.amazonaws.com/us-east-1_4Y1JyaYkC</string>
        <key>COGNITO_JWKS_URI</key>
        <string>https://cognito-idp.us-east-1.amazonaws.com/us-east-1_4Y1JyaYkC/.well-known/jwks.json</string>
        <key>MCP_RESOURCE_URL</key>
        <string>https://eviebot.tailf90db7.ts.net</string>
        <key>COGNITO_PUBLIC_CLIENT_ID</key>
        <string>2m0mavh487mal44dgrd9vkr07a</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/evehwang/Library/Logs/mcp-gateway/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/evehwang/Library/Logs/mcp-gateway/stderr.log</string>
</dict>
</plist>
```

### 6.2 Load and Start

```bash
mkdir -p ~/Library/Logs/mcp-gateway
launchctl load ~/Library/LaunchAgents/com.evie.mcp-gateway.plist
launchctl start com.evie.mcp-gateway
```

### 6.3 Verify Funnel Persistence

```bash
# Funnel with --bg should already persist
tailscale serve status
```

### 6.4 Human Task

**Human task:** Verify full flow after reboot (GitHub issue #6)

---

## Implementation Sequence Summary

| Phase | What | Depends On | Estimated Effort |
|-------|------|------------|-----------------|
| 1 | Discovery | — | **Done** |
| 2 | Gateway (no auth) | Phase 1 | Build + test |
| 3 | Tailscale reconfig | Phase 2 | Quick config change |
| 4 | Cognito setup | Phase 3 | May already be done (existing setup) |
| 5 | Gateway auth | Phases 2 + 4 | Build + human testing |
| 6 | Persistent service | Phase 5 | Config + reboot test |
