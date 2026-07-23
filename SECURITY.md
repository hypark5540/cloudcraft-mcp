# Security Policy

## Supported versions

Security fixes are released for the latest published version only.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | Yes       |
| < 0.1   | No        |

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting form:

<https://github.com/hypark5540/cloudcraft-mcp/security/advisories/new>

Do not open a public issue for a vulnerability or include a Cloudcraft API key
in a report. Include the affected version, impact, reproduction steps, and any
suggested mitigation. You should receive an acknowledgement within seven days.

## Secret handling

`CLOUDCRAFT_API_KEY` grants access to the Cloudcraft account associated with
it. Keep it in the MCP client's secret store or process environment, never in
source control, command-line arguments, issue reports, or logs. Rotate a key
immediately if it may have been exposed.
