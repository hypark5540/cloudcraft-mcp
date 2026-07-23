import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmod,
  copyFile,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { unzipSync, zipSync } from "fflate";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const defaultOutput = resolve(
  root,
  `release-artifacts/mcpb/cloudcraft-mcp-${packageJson.version}.mcpb`,
);
const fixedZipDate = new Date(1980, 0, 1, 0, 0, 0);
const sourceEntries = new Map([
  ["LICENSE", { source: "LICENSE", mode: 0o644 }],
  ["PRIVACY.md", { source: "PRIVACY.md", mode: 0o644 }],
  ["README.md", { source: "README.md", mode: 0o644 }],
  ["manifest.json", { source: "mcpb/manifest.json", mode: 0o644 }],
  ["pyproject.toml", { source: "pyproject.toml", mode: 0o644 }],
  ["uv.lock", { source: "uv.lock", mode: 0o644 }],
  [
    "src/cloudcraft_mcp/__init__.py",
    { source: "src/cloudcraft_mcp/__init__.py", mode: 0o644 },
  ],
  [
    "src/cloudcraft_mcp/__main__.py",
    { source: "src/cloudcraft_mcp/__main__.py", mode: 0o644 },
  ],
  [
    "src/cloudcraft_mcp/client.py",
    { source: "src/cloudcraft_mcp/client.py", mode: 0o644 },
  ],
  [
    "src/cloudcraft_mcp/py.typed",
    { source: "src/cloudcraft_mcp/py.typed", mode: 0o644 },
  ],
  [
    "src/cloudcraft_mcp/server.py",
    { source: "src/cloudcraft_mcp/server.py", mode: 0o644 },
  ],
  [
    "src/cloudcraft_mcp/types.py",
    { source: "src/cloudcraft_mcp/types.py", mode: 0o644 },
  ],
]);

function parseOutputArgument(args) {
  if (args.length === 0) return defaultOutput;
  if (args.length === 2 && args[0] === "--output" && args[1]) {
    return resolve(root, args[1]);
  }
  throw new Error("Usage: node scripts/build-mcpb.mjs [--output <file.mcpb>]");
}

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

async function stageBundle(stageDirectory) {
  for (const [archivePath, entry] of sourceEntries) {
    const destination = resolve(stageDirectory, archivePath);
    await mkdir(dirname(destination), { recursive: true });
    await copyFile(resolve(root, entry.source), destination);
    await chmod(destination, entry.mode);
  }
}

function assertCandidateEntries(entries) {
  const actual = Object.keys(entries).sort();
  const expected = [...sourceEntries.keys()].sort();
  if (
    actual.length !== expected.length ||
    actual.some((entry, index) => entry !== expected[index])
  ) {
    throw new Error(
      `Unexpected MCPB contents: ${actual.join(", ")} (expected ${expected.join(", ")}).`,
    );
  }
}

function normalizeCandidate(candidate) {
  const unpacked = unzipSync(candidate);
  assertCandidateEntries(unpacked);

  const normalized = {};
  for (const archivePath of [...sourceEntries.keys()].sort()) {
    const { mode } = sourceEntries.get(archivePath);
    normalized[archivePath] = [
      unpacked[archivePath],
      {
        level: 9,
        mtime: fixedZipDate,
        os: 3,
        attrs: mode << 16,
      },
    ];
  }
  return zipSync(normalized, { level: 9, mtime: fixedZipDate });
}

const output = parseOutputArgument(process.argv.slice(2));
const manifest = JSON.parse(
  await readFile(resolve(root, "mcpb/manifest.json"), "utf8"),
);
if (manifest.version !== packageJson.version) {
  throw new Error(
    `MCPB manifest version ${String(manifest.version)} does not match package ${packageJson.version}.`,
  );
}

const temporaryRoot = await mkdtemp(resolve(tmpdir(), "cloudcraft-mcp-mcpb-"));
const stageDirectory = resolve(temporaryRoot, "stage");
const candidatePath = resolve(temporaryRoot, "candidate.mcpb");
const temporaryOutput = `${output}.${process.pid}.tmp`;
const mcpbCli = resolve(
  root,
  "node_modules/@anthropic-ai/mcpb/dist/cli/cli.js",
);

try {
  await mkdir(stageDirectory, { recursive: true });
  await stageBundle(stageDirectory);
  await run(process.execPath, [mcpbCli, "validate", stageDirectory]);
  await run(process.execPath, [
    mcpbCli,
    "pack",
    stageDirectory,
    candidatePath,
  ]);

  const normalized = normalizeCandidate(await readFile(candidatePath));
  await mkdir(dirname(output), { recursive: true });
  await writeFile(temporaryOutput, normalized, { mode: 0o644 });
  await rm(output, { force: true });
  await rename(temporaryOutput, output);
  await chmod(output, 0o644);

  const digest = createHash("sha256").update(normalized).digest("hex");
  console.log(
    `Deterministic MCPB written: ${relative(root, output)} (sha256 ${digest})`,
  );
} finally {
  await rm(temporaryOutput, { force: true });
  await rm(temporaryRoot, { recursive: true, force: true });
}
