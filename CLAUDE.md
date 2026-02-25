# CLAUDE.md — eviebot-MCP-gateway

## Project

MCP Gateway for Eviebot — a single HTTPS endpoint that aggregates multiple MCP servers behind OAuth 2.1 authentication. Claude.ai connects to one URL and gets access to all backend MCP tools.

## Sources of Truth

- **Specification:** `docs/spec.md` — what we're building and why
- **Plan:** `docs/plan.md` — how we're building it (phased, discovery-first)
- **Original spec:** `initial_spec` — the original artifact (preserved as-is)

## Stack

- **Gateway:** [TBD — decided after Phase 1 discovery: mcp-proxy, FastMCP proxy, or mcp-front]
- **Auth:** AWS Cognito (OAuth 2.1, custom domain auth.evehuang.com)
- **Networking:** Tailscale Funnel (port 443 → gateway on localhost:8080)
- **Backend servers:** Existing FastMCP (Python) servers, unchanged
- **Service management:** launchd (macOS)

## MCP Gateway Architecture

Eviebot runs multiple MCP servers behind a single MCP gateway. The gateway is the
only service exposed to the internet (via Tailscale Funnel on port 443). Individual
MCP servers bind to localhost only and are never directly internet-accessible.

### Gateway

- Location: [TBD — post-discovery]
- Config: [TBD — post-discovery]
- Local port: 8080
- Exposed via: Tailscale Funnel (https://eviebot.tailf90db7.ts.net)
- Auth: OAuth 2.1 via AWS Cognito (auth.evehuang.com)
- Runs as: launchd service

### Registered MCP Servers

| Name | Port | Repo | Description |
|------|------|------|-------------|
| fastmail | [TBD] | [TBD] | Email read/search via JMAP |
| music | [TBD] | [TBD] | Apple Music playlists and discovery |

### Adding a New MCP Server

1. Build the server to bind to localhost on port [next available]
2. Do NOT implement authentication — the gateway handles this
3. Add entry to gateway config: [TBD — path to config file]
4. Create launchd plist in ~/Library/LaunchAgents/
5. Restart the gateway: [TBD — restart command]
6. Test: verify new tools appear via gateway tool listing

### Port Allocation

- 8080: MCP Gateway
- [TBD]: Fastmail MCP server (existing)
- [TBD]: Music MCP server (existing)
- 3001+: Future MCP servers (assign sequentially)

### Tool Naming Convention

Tools are namespaced by server name at the gateway level. When building a new
server, use descriptive tool names without a prefix — the gateway adds the prefix
automatically (e.g., a tool named `search_emails` on the `fastmail` server becomes
`fastmail_search_emails` in the aggregated catalog).

## Development Notes

- Discovery and build happen on Eviebot (Mac mini, headless)
- The two existing MCP servers must NOT be modified
- Password-gate on existing servers stays as defense-in-depth
