import { spawn } from "node:child_process";

const [command, ...args] = process.argv.slice(2);
if (!command) {
  console.error("Usage: node scripts/smoke-stdio.mjs <command> [args ...]");
  process.exit(2);
}

const expectedTools = [
  "create_blueprint",
  "delete_blueprint",
  "export_blueprint_image",
  "get_blueprint",
  "list_aws_accounts",
  "list_blueprints",
  "snapshot_aws",
  "update_blueprint",
  "whoami",
].sort();
const child = spawn(command, args, {
  env: {
    ...process.env,
    CLOUDCRAFT_API_KEY:
      process.env.CLOUDCRAFT_API_KEY || "cloudcraft-mcp-smoke-test-key",
  },
  stdio: ["pipe", "pipe", "pipe"],
  windowsHide: true,
});

let stdout = "";
let stderr = "";
let settled = false;

const timeout = setTimeout(() => {
  finish(new Error(`MCP smoke test timed out. stderr: ${stderr}`));
}, 30_000);

function finish(error) {
  if (settled) return;
  settled = true;
  clearTimeout(timeout);
  if (!child.killed) child.kill("SIGTERM");
  const forceKill = setTimeout(() => {
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGKILL");
  }, 2_000);
  forceKill.unref();
  if (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}

function send(message) {
  child.stdin.write(`${JSON.stringify(message)}\n`);
}

child.once("error", finish);
child.once("exit", (code, signal) => {
  if (!settled) {
    finish(
      new Error(
        `MCP server exited before completing the smoke test (${signal ?? `code ${String(code)}`}). stderr: ${stderr}`,
      ),
    );
  }
});
child.stdin.on("error", (error) => {
  if (!settled) finish(error);
});
child.stderr.setEncoding("utf8");
child.stderr.on("data", (chunk) => {
  stderr = `${stderr}${chunk}`.slice(-20_000);
});
child.stdout.setEncoding("utf8");
child.stdout.on("data", (chunk) => {
  stdout += chunk;
  const lines = stdout.split("\n");
  stdout = lines.pop() ?? "";

  for (const line of lines) {
    if (!line.trim()) continue;

    let response;
    try {
      response = JSON.parse(line);
    } catch {
      finish(new Error(`Server wrote non-JSON data to stdout: ${line}`));
      return;
    }
    if (response.error) {
      finish(new Error(`MCP server returned an error: ${line}`));
      return;
    }

    if (response.id === 1) {
      if (!response.result?.serverInfo) {
        finish(new Error(`Invalid initialize response: ${line}`));
        return;
      }
      send({ jsonrpc: "2.0", method: "notifications/initialized" });
      send({ jsonrpc: "2.0", id: 2, method: "tools/list", params: {} });
    } else if (response.id === 2) {
      const names = (response.result?.tools ?? [])
        .map((tool) => tool?.name)
        .sort();
      if (JSON.stringify(names) !== JSON.stringify(expectedTools)) {
        finish(
          new Error(
            `Unexpected MCP tools: ${names.join(", ")} (expected ${expectedTools.join(", ")}).`,
          ),
        );
        return;
      }
      console.log(
        `MCP stdio smoke passed: ${names.length} tools (${command} ${args.join(" ")})`,
      );
      finish();
    }
  }
});

send({
  jsonrpc: "2.0",
  id: 1,
  method: "initialize",
  params: {
    protocolVersion: "2025-06-18",
    capabilities: {},
    clientInfo: { name: "cloudcraft-mcp-smoke", version: "1.0.0" },
  },
});
