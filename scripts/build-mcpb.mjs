import { createHash } from "node:crypto";
import { chmod, mkdir, readFile, rename, rm, writeFile } from "node:fs/promises";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { zipSync } from "fflate";

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

// The MCPB format is a plain ZIP with manifest.json at the root. Building it
// directly with fflate keeps the archive byte-for-byte reproducible and drops
// the @anthropic-ai/mcpb CLI (and its node-forge dependency tree) for a `pack`
// step whose output was re-zipped here anyway. CI validates mcpb/manifest.json
// against the official v0.4 JSON schema with check-jsonschema.
async function buildArchive() {
  const entries = {};
  for (const archivePath of [...sourceEntries.keys()].sort()) {
    const { source, mode } = sourceEntries.get(archivePath);
    entries[archivePath] = [
      new Uint8Array(await readFile(resolve(root, source))),
      { level: 9, mtime: fixedZipDate, os: 3, attrs: mode << 16 },
    ];
  }
  return zipSync(entries, { level: 9, mtime: fixedZipDate });
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

const temporaryOutput = `${output}.${process.pid}.tmp`;

try {
  const archive = await buildArchive();
  await mkdir(dirname(output), { recursive: true });
  await writeFile(temporaryOutput, archive, { mode: 0o644 });
  await rm(output, { force: true });
  await rename(temporaryOutput, output);
  await chmod(output, 0o644);

  const digest = createHash("sha256").update(archive).digest("hex");
  console.log(
    `Deterministic MCPB written: ${relative(root, output)} (sha256 ${digest})`,
  );
} finally {
  await rm(temporaryOutput, { force: true });
}
