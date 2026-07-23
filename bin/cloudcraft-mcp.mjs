#!/usr/bin/env node

import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const packageRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const metadata = JSON.parse(
  readFileSync(resolve(packageRoot, "package.json"), "utf8"),
);
const wheel = resolve(
  packageRoot,
  "npm",
  "vendor",
  `cloudcraft_mcp-${metadata.version}-py3-none-any.whl`,
);

if (!existsSync(wheel)) {
  console.error(`cloudcraft-mcp: bundled wheel is missing: ${wheel}`);
  process.exit(1);
}

const uv = process.env.CLOUDCRAFT_MCP_UV || "uv";
const args = [
  "tool",
  "run",
  "--isolated",
  "--from",
  wheel,
  "cloudcraft-mcp",
  ...process.argv.slice(2),
];
const child = spawn(uv, args, {
  env: process.env,
  stdio: "inherit",
  windowsHide: true,
});

let settled = false;

child.once("error", (error) => {
  if (settled) return;
  settled = true;
  if (error && error.code === "ENOENT") {
    console.error(
      "cloudcraft-mcp: uv was not found. Install it from https://docs.astral.sh/uv/getting-started/installation/ or set CLOUDCRAFT_MCP_UV to its path.",
    );
    process.exitCode = 127;
    return;
  }
  console.error(`cloudcraft-mcp: failed to start uv: ${error.message}`);
  process.exitCode = 1;
});

child.once("exit", (code, signal) => {
  if (settled) return;
  settled = true;
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (!settled && !child.killed) child.kill(signal);
  });
}
