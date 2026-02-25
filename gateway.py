"""MCP Gateway — aggregates Eviebot's MCP servers behind a single endpoint.

Mounts multiple backend MCP servers with namespaced tool names.
Authenticates via AWS Cognito (OAuth 2.1) and passes Bearer tokens
through to backends automatically.
"""

from fastmcp import FastMCP
from fastmcp.server import create_proxy
from starlette.middleware import Middleware

from auth import SlashNormalizationMiddleware, create_auth_provider

gateway = FastMCP(
    name="Eviebot MCP Gateway",
    auth=create_auth_provider(),
)

# Mount backend servers with namespaced tool names.
# The proxy transport automatically forwards the Authorization header
# from incoming requests to the backend servers (both backends validate
# the same Cognito JWTs).
fastmail = create_proxy("http://localhost:8000/mcp")
gateway.mount(fastmail, namespace="fastmail")

music = create_proxy("http://localhost:3000/mcp")
gateway.mount(music, namespace="music")

if __name__ == "__main__":
    gateway.run(
        transport="streamable-http",
        host="127.0.0.1",
        port=8080,
        middleware=[Middleware(SlashNormalizationMiddleware)],
    )
