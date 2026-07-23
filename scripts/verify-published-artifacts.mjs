import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { basename, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const pyproject = await readFile(resolve(root, "pyproject.toml"), "utf8");
const pypiName = pyproject.match(/^name\s*=\s*"([^"]+)"/m)?.[1];
const [registry, ...artifacts] = process.argv.slice(2);

if (!pypiName || !["npm", "pypi"].includes(registry) || artifacts.length === 0) {
  console.error(
    "Usage: node scripts/verify-published-artifacts.mjs <npm|pypi> <artifact...>",
  );
  process.exit(2);
}

async function digest(path, algorithm, encoding = "hex") {
  return createHash(algorithm).update(await readFile(path)).digest(encoding);
}

async function fetchMetadata(url) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal: AbortSignal.timeout(15_000),
  });
  if (response.status === 404) return undefined;
  if (!response.ok) {
    throw new Error(`Registry metadata request failed (${response.status}): ${url}`);
  }
  return response.json();
}

async function verifyNpm() {
  if (artifacts.length !== 1 || !artifacts[0].endsWith(".tgz")) {
    throw new Error("npm verification expects exactly one .tgz artifact.");
  }
  const url =
    `https://registry.npmjs.org/${encodeURIComponent(packageJson.name)}/` +
    encodeURIComponent(packageJson.version);
  const metadata = await fetchMetadata(url);
  if (!metadata) return "missing";

  const localIntegrity = `sha512-${await digest(artifacts[0], "sha512", "base64")}`;
  if (metadata.dist?.integrity !== localIntegrity) {
    throw new Error(
      `Published npm integrity differs for ${packageJson.name}@${packageJson.version}.`,
    );
  }
  return "matching";
}

async function verifyPypi() {
  const url =
    `https://pypi.org/pypi/${encodeURIComponent(pypiName)}/` +
    `${encodeURIComponent(packageJson.version)}/json`;
  const metadata = await fetchMetadata(url);
  if (!metadata) return "missing";
  if (!Array.isArray(metadata.urls)) {
    throw new Error(`PyPI returned invalid file metadata for ${pypiName}.`);
  }

  const localByFilename = new Map();
  for (const artifact of artifacts) {
    const filename = basename(artifact);
    if (localByFilename.has(filename)) {
      throw new Error(`Duplicate local PyPI artifact filename: ${filename}.`);
    }
    localByFilename.set(filename, await digest(artifact, "sha256"));
  }

  const remoteByFilename = new Map();
  for (const entry of metadata.urls) {
    if (
      typeof entry.filename !== "string" ||
      typeof entry.digests?.sha256 !== "string" ||
      remoteByFilename.has(entry.filename)
    ) {
      throw new Error(`PyPI returned invalid or duplicate file metadata for ${pypiName}.`);
    }
    remoteByFilename.set(entry.filename, entry.digests.sha256);
  }

  for (const [filename, remoteSha256] of remoteByFilename) {
    const localSha256 = localByFilename.get(filename);
    if (localSha256 === undefined) {
      throw new Error(
        `Published PyPI contains an unexpected file for this release: ${filename}.`,
      );
    }
    if (remoteSha256 !== localSha256) {
      throw new Error(`Published PyPI digest differs for ${filename}.`);
    }
  }

  return remoteByFilename.size === localByFilename.size
    ? "matching"
    : "missing";
}

try {
  const status = registry === "npm" ? await verifyNpm() : await verifyPypi();
  process.stdout.write(`${status}\n`);
} catch (error) {
  console.error(error instanceof Error ? error.message : String(error));
  process.exitCode = 1;
}
