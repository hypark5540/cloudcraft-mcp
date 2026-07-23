# Privacy

Cloudcraft MCP is an unofficial, local Model Context Protocol server. It does
not operate a hosted service and does not send telemetry to the maintainer.

When a tool is invoked, the server sends the data required for that operation
to the Cloudcraft API endpoint configured by `CLOUDCRAFT_BASE_URL` (Cloudcraft's
official API by default). Tool results are returned to the MCP host that
launched the process. Exported diagrams are written only below
`CLOUDCRAFT_EXPORT_DIR`, which defaults to a process-private subdirectory of
the operating system's temporary directory.

The server reads `CLOUDCRAFT_API_KEY` from its process environment and uses it
as a Bearer credential for Cloudcraft API requests. It does not intentionally
log or persist the key. The MCP host, Cloudcraft, and any custom proxy or base
URL have their own privacy and retention policies.

This project is not affiliated with Cloudcraft or Amazon Web Services.
