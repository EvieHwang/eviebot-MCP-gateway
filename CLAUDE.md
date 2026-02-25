# CLAUDE.md — eviebot-MCP-gateway

## Project

MCP Gateway for Eviebot — a single HTTPS endpoint that aggregates multiple MCP servers behind OAuth 2.1 authentication. Claude.ai connects to one URL and gets access to all backend MCP tools.

## Sources of Truth

- **Specification:** `docs/spec.md` — what we're building and why
- **Plan:** `docs/plan.md` — how we're building it (phased, discovery-first)
- **Original spec:** `initial_spec` — the original artifact (preserved as-is)

## Stack

- **Gateway:** [TBD — see evaluation in docs/plan.md Phase 1.7]
- **Auth:** AWS Cognito (OAuth 2.1, User Pool `us-east-1_4Y1JyaYkC`, custom domain auth.evehuang.com)
- **Networking:** Tailscale Funnel (port 443 → gateway on localhost:8080)
- **Backend servers:** FastMCP (Python) + MCP SDK (Node.js/TypeScript)
- **Service management:** launchd (macOS)

## MCP Gateway Architecture

Eviebot runs multiple MCP servers behind a single MCP gateway. The gateway is the
only service exposed to the internet (via Tailscale Funnel on port 443). Individual
MCP servers bind to localhost only and are never directly internet-accessible.

### Gateway

- Location: [TBD — post Phase 2]
- Config: [TBD — post Phase 2]
- Local port: 8080
- Exposed via: Tailscale Funnel (https://eviebot.tailf90db7.ts.net)
- Auth: OAuth 2.1 via AWS Cognito (auth.evehuang.com)
- Runs as: launchd service

### Registered MCP Servers

| Name | Port | Repo | Framework | Transport | LaunchAgent |
|------|------|------|-----------|-----------|-------------|
| fastmail | 8000 | ~/projects/fastmail-mcp-server | FastMCP 3.0.2 (Python) | Streamable HTTP (`/mcp`) | com.evie.fastmail-mcp |
| music | 3000 | ~/projects/mood-playlist-mcp | @modelcontextprotocol/sdk 1.27 (Node/TS) | Streamable HTTP (`/mcp`) | com.mood-playlist-mcp |

### Current Tailscale Funnel Config

```
https://eviebot.tailf90db7.ts.net     → http://127.0.0.1:8000 (Fastmail)
https://eviebot.tailf90db7.ts.net:8443 → http://127.0.0.1:3000 (Music)
```

The gateway will consolidate both into a single port 443 → localhost:8080.

### Existing Auth

Both servers already implement full OAuth 2.1 with Cognito:
- Fastmail: Custom `CognitoAuthProvider` in `auth.py`, validates JWTs via JWKS
- Music: `MoodPlaylistOAuthProvider` in `src/auth/oauth-provider.ts`
- Cognito User Pool: `us-east-1_4Y1JyaYkC`
- Public Client ID: `2m0mavh487mal44dgrd9vkr07a`

The gateway must either:
1. Reuse the same Cognito setup (validate tokens at gateway, pass through to backends)
2. Or bypass backend auth entirely since backends will be localhost-only

### Adding a New MCP Server

1. Build the server to bind to localhost on the next available port
2. Do NOT implement authentication — the gateway handles this
3. Add entry to gateway config: [TBD — path to config file]
4. Create launchd plist in ~/Library/LaunchAgents/
5. Restart the gateway: [TBD — restart command]
6. Test: verify new tools appear via gateway tool listing

### Port Allocation

- 8080: MCP Gateway (planned)
- 8000: Fastmail MCP server (existing, localhost only)
- 3000: Music MCP server (existing, `*:3000`)
- 3001+: Future MCP servers (assign sequentially)

### Tool Naming Convention

Tools are namespaced by server name at the gateway level. When building a new
server, use descriptive tool names without a prefix — the gateway adds the prefix
automatically (e.g., a tool named `search_emails` on the `fastmail` server becomes
`fastmail_search_emails` in the aggregated catalog).

## Development Notes

- Discovery and build happen on Eviebot (Mac mini, headless)
- The two existing MCP servers must NOT be modified
- Both servers already have Cognito OAuth — the gateway can reuse this infrastructure
- Fastmail binds to localhost:8000; Music binds to *:3000 (both behind Funnel currently)
