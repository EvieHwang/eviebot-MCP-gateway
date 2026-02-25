# MCP Gateway

A single MCP gateway that aggregates multiple [Model Context Protocol](https://modelcontextprotocol.io/) servers behind one authenticated HTTPS endpoint. Connect Claude.ai (or any MCP client) to one URL and get access to all your tools.

Built with [FastMCP](https://github.com/jlowin/fastmcp) proxy mode, authenticated via AWS Cognito (OAuth 2.1), and exposed to the internet through [Tailscale Funnel](https://tailscale.com/kb/1223/funnel).

## Architecture

```
Claude.ai / Claude Mobile
      │
      │ HTTPS + Bearer token (Cognito JWT)
      ▼
Tailscale Funnel (port 443)
      │
      ▼
MCP Gateway (localhost:8080)
   ├── OAuth 2.1 token validation (Cognito JWKS)
   ├── RFC 9728 Protected Resource Metadata
   ├── RFC 8414 OAuth AS Metadata (proxied from Cognito)
   ├── Dynamic Client Registration (DCR)
   ├── Aggregated tool catalog (namespaced per server)
   └── Request routing → correct backend
      │
      ├──localhost──▶ Fastmail MCP Server (:8000)
      ├──localhost──▶ Music MCP Server (:3000)
      └──localhost──▶ Future servers (:3001+)
```

## How it works

1. The gateway connects to each backend MCP server and collects their tool lists
2. Tool names are automatically prefixed with the server namespace (e.g., `list_emails` → `fastmail_list_emails`)
3. Claude sees one unified tool catalog and picks tools based on the conversation
4. When Claude calls a tool, the gateway routes it to the correct backend by namespace
5. Authentication happens once at the gateway — backends receive forwarded credentials

## Features

- **Tool aggregation** — Multiple MCP servers appear as one to the client
- **Automatic namespacing** — No tool name collisions between servers
- **OAuth 2.1** — Cognito JWT validation with PKCE, DCR, and all the well-known endpoints Claude.ai expects
- **Flexible backend auth** — Supports both token pass-through (for backends that accept the same JWT) and service token minting (for backends with their own auth)
- **Zero backend modifications** — Existing MCP servers run unchanged
- **Survives reboots** — Runs as a macOS launchd service

## Setup

### Prerequisites

- Python 3.12+
- [Tailscale](https://tailscale.com/) with Funnel enabled
- AWS Cognito User Pool (or adapt `auth.py` for your OAuth provider)
- One or more MCP servers running on localhost

### Install

```bash
git clone https://github.com/EvieHwang/eviebot-MCP-gateway.git
cd eviebot-MCP-gateway
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure

Create a `.env` file (or set environment variables):

```bash
COGNITO_ISSUER_URL=https://cognito-idp.us-east-1.amazonaws.com/YOUR_POOL_ID
COGNITO_JWKS_URI=https://cognito-idp.us-east-1.amazonaws.com/YOUR_POOL_ID/.well-known/jwks.json
MCP_RESOURCE_URL=https://your-public-url.example.com
COGNITO_PUBLIC_CLIENT_ID=your_cognito_app_client_id

# Only needed if a backend uses its own JWT auth (not Cognito)
MUSIC_JWT_SECRET=your_backend_jwt_secret
```

### Add backend servers

Edit `gateway.py` to mount your MCP servers:

```python
from fastmcp import FastMCP
from fastmcp.server import create_proxy

gateway = FastMCP(name="My MCP Gateway", auth=create_auth_provider())

# Simple pass-through: the gateway forwards the client's Bearer token
server_a = create_proxy("http://localhost:8000/mcp")
gateway.mount(server_a, namespace="server_a")

# Custom auth: mint a service token for backends with their own JWT auth
# (see gateway.py for the full pattern with ProxyClient + StreamableHttpTransport)
```

### Run

```bash
python gateway.py
# Gateway starts on http://127.0.0.1:8080
```

### Expose via Tailscale Funnel

```bash
tailscale serve --bg --https=443 http://localhost:8080
tailscale funnel --bg --https=443 on
```

### Connect Claude.ai

1. Go to **Settings → Connectors** in claude.ai
2. Add a custom connector with your Funnel URL (e.g., `https://your-host.ts.net/mcp`)
3. Complete the OAuth flow when prompted
4. All tools from all backend servers appear in your conversations

## Backend auth strategies

The gateway supports two strategies for authenticating with backend servers:

### Token pass-through (default)

If your backend accepts the same Cognito JWTs as the gateway, FastMCP's proxy automatically forwards the `Authorization` header. No extra configuration needed — just `create_proxy()` and `mount()`.

### Service token minting

If a backend uses its own auth (different JWT issuer, shared secret, API key), the gateway can mint credentials per-session. The `gateway.py` file demonstrates this with `ProxyClient` and `StreamableHttpTransport`:

```python
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server.providers.proxy import FastMCPProxy, ProxyClient

def _client_factory():
    token = mint_your_token()  # your token-minting logic
    transport = StreamableHttpTransport("http://localhost:3000/mcp", auth=token)
    return ProxyClient(transport)

proxy = FastMCPProxy(client_factory=_client_factory)
gateway.mount(proxy, namespace="my_server")
```

## Adding a new backend server

1. Build your MCP server to bind to localhost on the next available port
2. Do **not** implement authentication — the gateway handles it
3. Add a `create_proxy()` + `gateway.mount()` call in `gateway.py`
4. Restart the gateway
5. New tools appear automatically in Claude.ai — no connector changes needed

## Running as a persistent service (macOS)

Create a launchd plist at `~/Library/LaunchAgents/com.your-name.mcp-gateway.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.your-name.mcp-gateway</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/.venv/bin/python3</string>
        <string>gateway.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/eviebot-MCP-gateway</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>COGNITO_ISSUER_URL</key>
        <string>https://cognito-idp.us-east-1.amazonaws.com/YOUR_POOL_ID</string>
        <!-- ... other env vars ... -->
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/logs/stderr.log</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.your-name.mcp-gateway.plist
```

## Key files

| File | Purpose |
|------|---------|
| `gateway.py` | Main server — mounts backend proxies with namespaced tools |
| `auth.py` | Cognito OAuth provider — JWT validation, DCR, metadata endpoints |
| `.env` | Environment variables (not committed) |
| `docs/spec.md` | Full project specification |
| `docs/plan.md` | Implementation plan with discovery results |

## Gotchas

- **Pydantic AnyHttpUrl trailing slash**: `AnyHttpUrl("https://example.com")` becomes `"https://example.com/"`, which causes double-slash well-known URLs. The `SlashNormalizationMiddleware` in `auth.py` handles this.
- **Claude.ai connector URL must include `/mcp`**: Use `https://your-host.ts.net/mcp`, not just the base URL.
- **DCR is mandatory**: Even if you pre-register your client in Cognito, Claude.ai still calls the DCR endpoint. The gateway returns the pre-registered credentials.
- **Cognito OIDC metadata is incomplete**: Cognito doesn't advertise `code_challenge_methods_supported`, `grant_types_supported`, or `registration_endpoint`. The gateway augments the metadata with these fields.

## License

MIT
