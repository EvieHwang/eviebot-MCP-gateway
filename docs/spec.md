# MCP Gateway for Eviebot — Specification

**Project:** eviebot-MCP-gateway
**Date:** 2026-02-24
**Status:** Pre-Discovery

---

## Goal

Build a single MCP gateway on Eviebot (Mac mini) that aggregates multiple MCP servers behind one HTTPS endpoint. Claude.ai connects to one connector URL and gets access to all tools from all backend servers. New MCP servers are added by editing a config file — no changes needed in claude.ai.

The gateway also implements OAuth 2.1 authentication via AWS Cognito, replacing the current password-gate approach with proper token-based security.

## Current State

### Eviebot

- Mac mini (Apple Silicon), macOS Tahoe, always-on headless server
- Access: SSH/Mosh via Blink Shell on iPad, Tailscale for remote access
- Tailscale hostname: `eviebot.tailf90db7.ts.net`
- Tailscale IP: 100.73.184.13
- Installed: Node.js, Python, Homebrew, Claude Code, AWS CLI, git
- GitHub username: EvieHwang
- AWS account active with CLI configured
- Domain: EveHuang.com, managed on Route 53

### Existing MCP Servers (DO NOT MODIFY)

Two MCP servers are already running on Eviebot. These are complex implementations that must not be changed during this project. The gateway routes to them as-is.

**1. Fastmail MCP Server**

- Purpose: Email read/search via JMAP (list mailboxes, list emails, get email, search emails, get thread)
- Framework: FastMCP (Python)
- Local port: Determine from running processes or launchd config
- Repo: Check ~/projects/ or locate via launchd plist
- Current auth: Password-gate (each tool validates a `password` parameter)
- Current exposure: Tailscale Funnel → direct to this server
- Claude.ai connector URL: `https://eviebot.tailf90db7.ts.net/mcp`

**2. Apple Music / Mood Playlist MCP Server**

- Purpose: Apple Music integration for playlist creation and music discovery
- Framework: Determine from running processes
- Local port: Determine from running processes or launchd config
- Repo: Check ~/projects/ or locate via launchd plist
- Current auth: Password-gate (same approach as Fastmail)
- Current exposure: Tailscale Funnel → direct to this server
- Claude.ai connector URL: `https://eviebot.tailf90db7.ts.net`

### Important: Discovery Step

Before building anything, Claude Code must discover the exact state of both servers:

1. Check running processes: `ps aux | grep -i mcp`
1. Check launchd plists: `ls ~/Library/LaunchAgents/*mcp*` and `launchctl list | grep mcp`
1. Check Tailscale Funnel config: `tailscale serve status`
1. Identify local ports each server listens on
1. Identify repos and frameworks used
1. Verify both servers respond to tool listing (connect locally and call `tools/list`)
1. Document findings before proceeding

## Target Architecture

```
claude.ai / Claude Mobile
      │
      │ HTTPS (Streamable HTTP + Bearer token from Cognito)
      ▼
Tailscale Funnel (port 443 → localhost:8080)
      │
      ▼
MCP Gateway (localhost:8080)
   ├── OAuth token validation (JWT from Cognito via JWKS)
   ├── Protected Resource Metadata endpoint (RFC 9728)
   ├── Aggregated tool catalog (namespaced per server)
   ├── Request routing (by tool namespace → correct backend)
   └── Runs as launchd service
      │
      ├──localhost──▶ Fastmail MCP (existing port, unchanged)
      ├──localhost──▶ Music MCP (existing port, unchanged)
      └──localhost──▶ Future servers (port 300N)

AWS Cognito (Authorization Server)
   ├── User Pool with single user (Evie)
   ├── Custom domain: auth.evehuang.com
   ├── Pre-registered App Client (for claude.ai)
   ├── Hosted UI for one-time authentication
   ├── Issues JWTs validated by gateway
   └── PKCE + Authorization Code flow
```

### How It Works

1. Claude.ai connects to the gateway URL and asks for available tools
1. The gateway connects to each backend server, collects their tool lists, and prefixes each tool name with the server name (e.g., `fastmail_list_emails`, `music_create_playlist`)
1. Claude sees one unified tool catalog and picks tools based on the conversation
1. When Claude calls a tool, the gateway identifies which backend server owns it (by prefix), strips the prefix, forwards the call, and returns the result
1. Authentication happens once at the gateway — backend servers don't need to validate anything from the gateway (they're localhost-only)

## Gateway Technology Choice

### Recommended: mcp-proxy (sparfenyuk/mcp-proxy)

- Python-based, pip-installable (`pip install mcp-proxy`)
- Supports named servers via `--named-server` flag or JSON config file
- Named servers accessible under `/servers/<server-name>/` paths
- Supports both SSE and Streamable HTTP transports
- Actively maintained
- Lightweight — no Kubernetes, no Docker required

### Alternative: FastMCP proxy mode

- If the existing servers are built with FastMCP, its built-in proxy capabilities may be a better fit
- Evaluate during discovery step

### Alternative: mcp-front (stainless-api/mcp-front)

- Go binary with built-in OAuth/bearer auth support
- Designed specifically as an auth proxy for MCP servers
- Supports multiple transport types (stdio, SSE, streamable-http)
- May be a good fit if we want auth and routing in one package

### Decision

Claude Code should evaluate all three options during the discovery phase, considering:

1. Compatibility with the existing servers' transport types
1. Built-in auth support (mcp-front has this; mcp-proxy would need auth added separately)
1. Tool namespacing support
1. Ease of adding new servers via config
1. Python vs Go (Python is more consistent with the existing stack if servers are FastMCP)

## Authentication Strategy

### OAuth 2.1 with Pre-Registration via AWS Cognito

This is the proper implementation of what was originally specced but fell back to password-gate due to claude.ai OAuth bugs. The bugs (specifically: claude.ai not sending bearer tokens after OAuth completion) appear to be fixed as of February 2026. The original issue (modelcontextprotocol/modelcontextprotocol#2157) is now closed.

### Cognito Configuration

- **User Pool:** Single user (Evie), email-based login
- **App Client:** Pre-registered with fixed Client ID and Client Secret
- **Auth flow:** Authorization Code with PKCE (S256), required by MCP spec
- **Redirect URIs:** `https://claude.ai/api/mcp/auth_callback` AND `https://claude.com/api/mcp/auth_callback` (allowlist both)
- **Token settings:** Access token expiry ~1 hour, refresh token expiry ~30 days
- **Scopes:** `openid`, `email`
- **Custom domain:** `auth.evehuang.com` (requires ACM certificate in us-east-1)

### Cognito Custom Domain Setup

1. ACM certificate in **us-east-1** (N. Virginia) — mandatory regardless of User Pool region
1. Route 53 A record (alias) for `auth.evehuang.com` pointing to the CloudFront distribution Cognito creates
1. A parent A record for `evehuang.com` must exist in Route 53
1. Propagation: Custom domain takes ~5 minutes, CloudFront distribution up to 1 hour

### Gateway Auth Implementation

The gateway must:

- Serve the `.well-known/oauth-protected-resource` endpoint pointing to Cognito as the authorization server
- Validate incoming Bearer tokens as Cognito JWTs (check signature via JWKS, issuer, audience, expiry)
- Return 401 with proper WWW-Authenticate header for unauthenticated requests
- Support the MCP auth spec 2025-06-18

### Claude.ai Configuration (human step)

1. Settings → Connectors → Remove existing Fastmail and Music connectors
1. Add custom connector with the gateway's Tailscale Funnel URL
1. Advanced Settings → enter pre-registered Client ID and Client Secret from Cognito
1. Complete OAuth flow (one-time Cognito login at auth.evehuang.com)

### Fallback: Password-Gate

If OAuth still doesn't work in claude.ai (the pre-registration flow fails or tokens aren't sent), fall back to the existing password-gate approach. The gateway would accept a password parameter and validate it before routing to backend servers. The existing servers already implement password-gate, so this fallback requires no backend changes.

**Important:** Do not remove the password-gate from the existing servers during this project. It remains as a defense-in-depth layer and a fallback. It can be removed in a future cleanup once OAuth is confirmed working.

## Migration Plan

### Phase 1: Discovery and Validation

1. Discover exact state of both existing servers (ports, frameworks, repos, launchd configs)
1. Verify both servers respond correctly to local tool listing
1. Document current Tailscale Funnel/Serve configuration
1. Select gateway technology based on findings

### Phase 2: Gateway Setup (No Auth)

1. Install and configure the gateway
1. Add both existing servers as named backends
1. Verify the gateway correctly aggregates tools from both servers
1. Verify tool calls route correctly and return proper results
1. Test locally — gateway on port 8080, hitting both backends

### Phase 3: Tailscale Reconfiguration

1. Reconfigure Tailscale Funnel/Serve to point port 443 → gateway (port 8080)
1. Remove old Funnel configs that pointed directly to individual servers
1. Test: connect to the Funnel URL and verify tool listing works
1. At this point, claude.ai would work if configured as an authless connector (for validation only)

### Phase 4: Cognito Setup (Human Tasks Required)

1. Create Cognito User Pool via AWS CLI or Console
1. Create single user (Evie)
1. Create App Client with pre-registered Client ID and Secret
1. Set up custom domain (auth.evehuang.com) with ACM certificate
1. Configure redirect URIs for claude.ai

### Phase 5: Gateway Auth Integration

1. Add OAuth token validation to the gateway
1. Add `.well-known/oauth-protected-resource` endpoint
1. Test with MCP Inspector (obtain token via Inspector's OAuth flow, then verify tool calls work with Bearer token)
1. Test with claude.ai (remove old connectors, add gateway connector with Client ID/Secret in Advanced Settings)

### Phase 6: Persistent Service

1. Create launchd plist for the gateway
1. Ensure it starts on boot and restarts on failure
1. Verify Tailscale Funnel persists (should already with `--bg`)
1. Test full flow after reboot

## Non-Goals

- **Modifying existing MCP servers** — The Fastmail and Music servers are complex, working implementations. This project routes to them; it does not change them.
- **Multi-user support** — The gateway serves a single user (Evie). Cognito has one user in the pool. There is no need for user management, roles, or permissions.
- **General-purpose auth proxy** — This is purpose-built for MCP protocol aggregation, not a generic OAuth reverse proxy.
- **Dynamic Client Registration (DCR)** — Claude.ai uses pre-registered client credentials (Client ID + Secret entered in Advanced Settings). The gateway does not need to implement a DCR endpoint.
- **Server-side tool filtering** — All tools from all backend servers are exposed. There is no per-user or per-session tool filtering.

## Open Questions

1. **Server ports and frameworks** — What ports do the existing servers listen on? Is the Music server also FastMCP? (Resolved by Phase 1 discovery)
2. **Gateway technology choice** — mcp-proxy vs FastMCP proxy vs mcp-front? (Resolved by Phase 1 evaluation)
3. **OAuth e2e viability** — Will claude.ai correctly complete the pre-registration OAuth flow and send Bearer tokens? The bug (modelcontextprotocol/modelcontextprotocol#2157) is closed but untested with this setup. (Resolved by Phase 5 testing)
4. **Tool namespacing format** — Does the chosen gateway automatically namespace tools, or do we need to implement prefixing? (Resolved during Phase 2)

## Adding Future MCP Servers

When building a new MCP server for the gateway:

1. The server binds to `localhost` only on the next available port (3001, 3002, 3003…)
1. The server does NOT implement its own authentication — the gateway handles this
1. The server does NOT need Tailscale Funnel configuration — it's never exposed directly
1. Add the server to the gateway config file with a name and local URL
1. Restart the gateway
1. New tools appear automatically in claude.ai conversations — no connector changes needed
1. Create a launchd plist for the new server so it persists across reboots

## Constraints

- Evie is a PM, not a software engineer — she follows technical instructions and debugs with Claude's help but doesn't write code from scratch
- Access to Eviebot is via SSH from iPad (Blink Shell) — no GUI development tools
- The two existing MCP servers must not be modified during this project
- Stay within ToS for all services (Anthropic, Tailscale, Fastmail, AWS, Apple)

## Technical References

- mcp-proxy: https://github.com/sparfenyuk/mcp-proxy
- mcp-front: https://github.com/stainless-api/mcp-front (auth proxy for MCP)
- FastMCP proxy docs: https://github.com/jlowin/fastmcp (check proxy/gateway features)
- Anthropic MCP connector docs: https://support.claude.com/en/articles/11503834-building-custom-connectors-via-remote-mcp-servers
- MCP Authorization Spec (2025-06-18): https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization
- Claude.ai OAuth callback: https://claude.ai/api/mcp/auth_callback (also allowlist https://claude.com/api/mcp/auth_callback)
- Anthropic outbound IPs for MCP: https://docs.claude.com/en/api/ip-addresses (160.79.104.0/21)
- Tailscale Funnel docs: https://tailscale.com/kb/1223/funnel
- Closed OAuth bug (token not sent): https://github.com/modelcontextprotocol/modelcontextprotocol/issues/2157

## Success Criteria

1. One connector URL in claude.ai provides access to all tools from both existing servers
1. Tool calls to both Fastmail and Music servers work correctly through the gateway
1. OAuth authentication via Cognito protects the gateway endpoint
1. Adding a new MCP server requires only: config edit, launchd plist, gateway restart
1. No modifications to existing MCP server code
1. Everything survives Eviebot reboots (launchd services + Tailscale Funnel persistence)
