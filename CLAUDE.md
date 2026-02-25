# CLAUDE.md — eviebot-MCP-gateway

## Project

MCP Gateway for Eviebot — a single HTTPS endpoint that aggregates multiple MCP servers behind OAuth 2.1 authentication. Claude.ai connects to one URL and gets access to all backend MCP tools.

## Sources of Truth

- **Specification:** `docs/spec.md` — what we're building and why
- **Plan:** `docs/plan.md` — how we're building it (phased, discovery-first)
- **Original spec:** `initial_spec` — the original artifact (preserved as-is)

## Stack

- **Gateway:** FastMCP 3.0.2 proxy mode (`create_proxy` + `mount` with namespaces)
- **Auth:** AWS Cognito (OAuth 2.1, User Pool `us-east-1_4Y1JyaYkC`, custom domain auth.evehwang.com)
- **Networking:** Tailscale Funnel (port 443 → gateway on localhost:8080)
- **Backend servers:** FastMCP (Python) + MCP SDK (Node.js/TypeScript)
- **Service management:** launchd (macOS)

## Key Files

- `gateway.py` — Main gateway server, mounts backend proxies
- `auth.py` — Cognito OAuth provider (JWT validation, DCR, metadata endpoints)
- `.env` — Environment variables (Cognito config, not committed)

## MCP Gateway Architecture

Eviebot runs multiple MCP servers behind a single MCP gateway. The gateway is the
only service exposed to the internet (via Tailscale Funnel on port 443). Individual
MCP servers bind to localhost only and are never directly internet-accessible.

### Gateway

- Code: `gateway.py` + `auth.py`
- Local port: 8080
- Exposed via: Tailscale Funnel (https://eviebot.tailf90db7.ts.net)
- Auth: OAuth 2.1 via AWS Cognito (auth.evehwang.com)
- LaunchAgent: `com.evie.mcp-gateway`
- Logs: `~/Library/Logs/mcp-gateway/`

### Auth Flow

The gateway validates Cognito JWTs and automatically forwards the Authorization
header to backend servers (both backends already validate the same Cognito tokens).
This means no backend modifications are needed — the gateway is a transparent
auth proxy.

### Tailscale Funnel Config

```
https://eviebot.tailf90db7.ts.net → http://127.0.0.1:8080 (Gateway)
```

### Registered MCP Servers

| Name | Port | Repo | Framework | Transport | LaunchAgent |
|------|------|------|-----------|-----------|-------------|
| fastmail | 8000 | ~/projects/fastmail-mcp-server | FastMCP 3.0.2 (Python) | Streamable HTTP (`/mcp`) | com.evie.fastmail-mcp |
| music | 3000 | ~/projects/mood-playlist-mcp | @modelcontextprotocol/sdk 1.27 (Node/TS) | Streamable HTTP (`/mcp`) | com.mood-playlist-mcp |

### Adding a New MCP Server

1. Build the server to bind to localhost on the next available port (3001+)
2. Do NOT implement authentication — the gateway handles this
3. Add a `create_proxy` + `gateway.mount()` call in `gateway.py`
4. Create launchd plist in ~/Library/LaunchAgents/
5. Restart the gateway: `launchctl kickstart -k gui/$(id -u)/com.evie.mcp-gateway`
6. Test: verify new tools appear via gateway tool listing

### Port Allocation

- 8080: MCP Gateway
- 8000: Fastmail MCP server (existing, localhost only)
- 3000: Music MCP server (existing)
- 3001+: Future MCP servers (assign sequentially)

### Tool Naming Convention

Tools are namespaced by server name at the gateway level. When building a new
server, use descriptive tool names without a prefix — the gateway adds the prefix
automatically (e.g., a tool named `search_emails` on the `fastmail` server becomes
`fastmail_search_emails` in the aggregated catalog).

## Development Notes

- The two existing MCP servers must NOT be modified
- Both servers already have Cognito OAuth — gateway passes through Bearer tokens
- Cognito User Pool: `us-east-1_4Y1JyaYkC`, Public Client ID: `2m0mavh487mal44dgrd9vkr07a`
