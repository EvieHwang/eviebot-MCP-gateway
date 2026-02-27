"""MCP Gateway — aggregates Eviebot's MCP servers behind a single endpoint.

Mounts multiple backend MCP servers with namespaced tool names.
Authenticates via AWS Cognito (OAuth 2.1) and passes Bearer tokens
through to backends automatically.

The Fastmail backend accepts Cognito JWTs (same issuer), so token
pass-through works. The Music backend uses self-issued JWTs with a
shared secret, so the gateway mints a service token for it.
"""

import os
import time

import jwt
from fastmcp import FastMCP
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server import create_proxy
from fastmcp.server.providers.proxy import FastMCPProxy, ProxyClient
from starlette.middleware import Middleware

from auth import SlashNormalizationMiddleware, create_auth_provider

gateway = FastMCP(
    name="Eviebot MCP Gateway",
    auth=create_auth_provider(),
)

# --- Fastmail backend ---
# Accepts Cognito JWTs — the proxy auto-forwards the Authorization header.
fastmail = create_proxy("http://localhost:8000/mcp")
gateway.mount(fastmail, namespace="fastmail")

# --- Music backend ---
# Uses self-issued JWTs (HS256) with its own secret, not Cognito.
# We mint a long-lived service token that the proxy sends instead of
# forwarding the gateway's Cognito token.
music_jwt_secret = os.environ.get("MUSIC_JWT_SECRET", "")
music_server_url = "https://eviebot.tailf90db7.ts.net"

if music_jwt_secret:
    def _mint_music_token(secret=music_jwt_secret, url=music_server_url):
        """Mint a short-lived JWT the Music server will accept."""
        return jwt.encode(
            {
                "sub": "gateway",
                "scopes": ["mcp:tools"],
                "aud": url,
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,  # 1 hour
            },
            secret,
            algorithm="HS256",
        )

    # Create a client factory that mints a fresh token each time,
    # so expiry is never an issue across long-running gateway sessions.
    def _music_client_factory():
        transport = StreamableHttpTransport(
            "http://localhost:3000/mcp",
            auth=_mint_music_token(),
        )
        return ProxyClient(transport)

    music_proxy = FastMCPProxy(client_factory=_music_client_factory)
    gateway.mount(music_proxy, namespace="music")
else:
    # Fallback: try pass-through (will fail if Music server rejects Cognito JWTs)
    music = create_proxy("http://localhost:3000/mcp")
    gateway.mount(music, namespace="music")

# --- Filesystem backend ---
# No auth needed — gateway forwards Cognito token (backend ignores it).
filesystem = create_proxy("http://localhost:3001/mcp")
gateway.mount(filesystem, namespace="filesystem")

# --- GitHub backend ---
# Same pass-through pattern as Filesystem.
github = create_proxy("http://localhost:3002/mcp")
gateway.mount(github, namespace="github")

if __name__ == "__main__":
    gateway.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8080,
        middleware=[Middleware(SlashNormalizationMiddleware)],
    )
