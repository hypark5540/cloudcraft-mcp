import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { unzipSync } from "fflate";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const artifact = resolve(
  root,
  process.argv[2] ??
    `release-artifacts/mcpb/cloudcraft-mcp-${packageJson.version}.mcpb`,
);
const expectedEntries = new Map([
  ["LICENSE", "LICENSE"],
  ["PRIVACY.md", "PRIVACY.md"],
  ["README.md", "README.md"],
  ["manifest.json", "mcpb/manifest.json"],
  ["pyproject.toml", "pyproject.toml"],
  ["uv.lock", "uv.lock"],
  ["src/cloudcraft_mcp/__init__.py", "src/cloudcraft_mcp/__init__.py"],
  ["src/cloudcraft_mcp/__main__.py", "src/cloudcraft_mcp/__main__.py"],
  ["src/cloudcraft_mcp/client.py", "src/cloudcraft_mcp/client.py"],
  ["src/cloudcraft_mcp/py.typed", "src/cloudcraft_mcp/py.typed"],
  ["src/cloudcraft_mcp/server.py", "src/cloudcraft_mcp/server.py"],
  ["src/cloudcraft_mcp/types.py", "src/cloudcraft_mcp/types.py"],
]);

function run(command, args) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(command, args, {
      cwd: root,
      stdio: "inherit",
      windowsHide: true,
    });
    child.once("error", reject);
    child.once("exit", (code, signal) => {
      if (code === 0) {
        resolvePromise();
        return;
      }
      reject(
        new Error(
          `${command} ${args.join(" ")} failed (${signal ?? `code ${String(code)}`}).`,
        ),
      );
    });
  });
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function sha256(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

async function assertArchiveContents(contents) {
  const unpacked = unzipSync(contents);
  const actualPaths = Object.keys(unpacked).sort();
  const expectedPaths = [...expectedEntries.keys()].sort();
  assert(
    actualPaths.length === expectedPaths.length &&
      actualPaths.every((entry, index) => entry === expectedPaths[index]),
    `Unexpected MCPB entries: ${actualPaths.join(", ")}.`,
  );

  for (const [archivePath, sourcePath] of expectedEntries) {
    const source = await readFile(resolve(root, sourcePath));
    assert(
      Buffer.from(unpacked[archivePath]).equals(source),
      `${archivePath} does not match ${sourcePath}.`,
    );
  }

  const manifest = JSON.parse(
    Buffer.from(unpacked["manifest.json"]).toString("utf8"),
  );
  const apiKeyConfig = manifest.user_config?.cloudcraft_api_key;
  const enableWritesConfig = manifest.user_config?.enable_writes;
  const enableDeletesConfig = manifest.user_config?.enable_deletes;
  const mcpEnvironment = manifest.server?.mcp_config?.env ?? {};
  const userConfigKeys = Object.keys(manifest.user_config ?? {}).sort();
  const sensitiveKeys = Object.entries(manifest.user_config ?? {})
    .filter(([, config]) => config.sensitive === true)
    .map(([key]) => key);
  assert(manifest.manifest_version === "0.4", "MCPB must use manifest v0.4.");
  assert(
    manifest.version === packageJson.version,
    "MCPB version must match package.json.",
  );
  assert(
    manifest.server?.type === "uv" &&
      manifest.server?.entry_point === "src/cloudcraft_mcp/__main__.py",
    "MCPB must use the uv runtime and canonical Python entry point.",
  );
  assert(
    manifest.server?.mcp_config?.command === "uv" &&
      JSON.stringify(manifest.server?.mcp_config?.args) ===
        JSON.stringify([
          "run",
          "--directory",
          "${__dirname}",
          "--frozen",
          "cloudcraft-mcp",
        ]),
    "MCPB must run the bundled, locked Python project through uv.",
  );
  assert(
    JSON.stringify(userConfigKeys) ===
      JSON.stringify([
        "cloudcraft_api_key",
        "enable_deletes",
        "enable_writes",
      ]) &&
    sensitiveKeys.length === 1 &&
      sensitiveKeys[0] === "cloudcraft_api_key" &&
      apiKeyConfig?.type === "string" &&
      apiKeyConfig.required === true &&
      apiKeyConfig.sensitive === true &&
      apiKeyConfig.default === undefined,
    "MCPB must expose only the API key and mutation safety gates, with the API key as the sole sensitive value.",
  );
  assert(
    enableWritesConfig?.type === "boolean" &&
      enableWritesConfig.default === false &&
      enableWritesConfig.required !== true &&
      enableWritesConfig.sensitive !== true &&
      enableDeletesConfig?.type === "boolean" &&
      enableDeletesConfig.default === false &&
      enableDeletesConfig.required !== true &&
      enableDeletesConfig.sensitive !== true,
    "MCPB mutation safety gates must be optional, non-sensitive booleans disabled by default.",
  );
  assert(
    Object.keys(mcpEnvironment).length === 3 &&
      mcpEnvironment.CLOUDCRAFT_API_KEY ===
        "${user_config.cloudcraft_api_key}" &&
      mcpEnvironment.CLOUDCRAFT_ENABLE_WRITES ===
        "${user_config.enable_writes}" &&
      mcpEnvironment.CLOUDCRAFT_ENABLE_DELETES ===
        "${user_config.enable_deletes}",
    "MCPB environment must map only the API key and default-off mutation gates from user_config.",
  );
}

const temporaryRoot = await mkdtemp(
  resolve(tmpdir(), "cloudcraft-mcp-verify-mcpb-"),
);
const firstBuild = resolve(temporaryRoot, "first.mcpb");
const secondBuild = resolve(temporaryRoot, "second.mcpb");
const unpackDirectory = resolve(temporaryRoot, "unpacked");
const buildScript = resolve(root, "scripts/build-mcpb.mjs");
const smokeScript = resolve(root, "scripts/smoke-stdio.mjs");
const mcpbCli = resolve(
  root,
  "node_modules/@anthropic-ai/mcpb/dist/cli/cli.js",
);
const uv = process.env.CLOUDCRAFT_MCP_UV || "uv";

try {
  await run(process.execPath, [buildScript, "--output", firstBuild]);
  await run(process.execPath, [buildScript, "--output", secondBuild]);

  const [publishedContents, firstContents, secondContents] = await Promise.all([
    readFile(artifact),
    readFile(firstBuild),
    readFile(secondBuild),
  ]);
  assert(
    firstContents.equals(secondContents),
    `MCPB builds are not deterministic: ${sha256(firstContents)} != ${sha256(secondContents)}.`,
  );
  assert(
    publishedContents.equals(firstContents),
    `MCPB artifact is stale: ${sha256(publishedContents)} != ${sha256(firstContents)}.`,
  );
  await assertArchiveContents(publishedContents);

  await run(process.execPath, [
    mcpbCli,
    "unpack",
    artifact,
    unpackDirectory,
  ]);
  await run(process.execPath, [
    mcpbCli,
    "validate",
    resolve(unpackDirectory, "manifest.json"),
  ]);
  await run(process.execPath, [
    smokeScript,
    uv,
    "run",
    "--directory",
    unpackDirectory,
    "--frozen",
    "cloudcraft-mcp",
  ]);

  console.log(
    `MCPB verification passed: deterministic sha256 ${sha256(publishedContents)}`,
  );
} finally {
  await rm(temporaryRoot, { recursive: true, force: true });
}
