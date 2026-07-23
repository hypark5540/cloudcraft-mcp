import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");

async function read(relativePath) {
  return readFile(resolve(root, relativePath), "utf8");
}

function capture(contents, pattern, label) {
  const match = contents.match(pattern);
  if (!match?.[1]) throw new Error(`Could not read version from ${label}.`);
  return match[1];
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const packageJson = JSON.parse(await read("package.json"));
const packageLock = JSON.parse(await read("package-lock.json"));
const pyproject = await read("pyproject.toml");
const pythonInit = await read("src/cloudcraft_mcp/__init__.py");
const uvLock = await read("uv.lock");
const readme = await read("README.md");
const releaseGuide = await read("docs/releasing.md");
const clientGuide = await read("docs/clients.md");
const dockerfile = await read("Dockerfile");
const mcpExample = JSON.parse(await read("mcp.example.json"));
const geminiExtension = JSON.parse(await read("gemini-extension.json"));
const serverJson = JSON.parse(await read("server.json"));
const mcpbManifest = JSON.parse(await read("mcpb/manifest.json"));

const pythonProjectName = capture(
  pyproject,
  /^name\s*=\s*"([^"]+)"/m,
  "PyPI project name",
);
const pythonVersion = capture(
  pyproject,
  /^version\s*=\s*"([^"]+)"/m,
  "pyproject.toml",
);
const packageByRegistry = new Map();
for (const entry of serverJson.packages ?? []) {
  assert(
    typeof entry.registryType === "string" &&
      !packageByRegistry.has(entry.registryType),
    `server.json contains a duplicate or invalid registry type: ${String(entry.registryType)}.`,
  );
  packageByRegistry.set(entry.registryType, entry);
}
const npmPackage = packageByRegistry.get("npm");
const pypiPackage = packageByRegistry.get("pypi");
const ociPackage = packageByRegistry.get("oci");

assert(
  /^\d+\.\d+\.\d+$/.test(packageJson.version),
  "Automated releases require a stable SemVer package version.",
);
assert(
  packageJson.name === "@hypark5540/cloudcraft-mcp" &&
    packageJson.mcpName === "io.github.hypark5540/cloudcraft-mcp",
  "npm and MCP Registry package names must use the hypark5540 namespace.",
);
assert(
  packageJson.mcpName === serverJson.name,
  "package.json mcpName must match server.json name.",
);
assert(
  packageByRegistry.size === 3 && npmPackage && pypiPackage && ociPackage,
  "server.json must contain exactly one npm, PyPI, and OCI package.",
);
assert(
  npmPackage?.identifier === packageJson.name,
  "The server.json npm identifier must match package.json name.",
);
assert(
  pypiPackage?.identifier === pythonProjectName,
  "The server.json PyPI identifier must match pyproject.toml name.",
);
assert(
  ociPackage.identifier ===
    `ghcr.io/hypark5540/cloudcraft-mcp:${packageJson.version}`,
  "The server.json OCI identifier must use the versioned GHCR image.",
);
assert(
  [...packageByRegistry.values()].every(
    (entry) => entry.transport?.type === "stdio",
  ),
  "Every package in server.json must use stdio transport.",
);
assert(
  readme.includes(`<!-- mcp-name: ${serverJson.name} -->`),
  "README.md is missing the MCP Registry ownership marker.",
);
assert(
  dockerfile.includes(
    `io.modelcontextprotocol.server.name="${serverJson.name}"`,
  ),
  "Dockerfile is missing the MCP Registry ownership label.",
);
assert(
  packageLock.name === packageJson.name &&
    packageLock.version === packageJson.version &&
    packageLock.packages?.[""]?.name === packageJson.name &&
    packageLock.packages?.[""]?.version === packageJson.version,
  "package-lock.json root name/version must match package.json.",
);
assert(
  packageJson.dependencies === undefined ||
    Object.keys(packageJson.dependencies).length === 0,
  "The npm launcher must not gain runtime npm dependencies.",
);
assert(
  packageJson.bin?.["cloudcraft-mcp"] === "bin/cloudcraft-mcp.mjs" &&
    packageJson.bin?.["hypark-cloudcraft-mcp"] === "bin/cloudcraft-mcp.mjs",
  "Both npm commands must execute the shared uv launcher.",
);
assert(
  packageJson.scripts?.["deps:locked"] === "npm ci --ignore-scripts" &&
    packageJson.scripts?.["build:npm"] ===
      "node scripts/build-npm-wheel.mjs" &&
    packageJson.scripts?.prepack ===
      "npm run check:versions && npm run build:npm",
  "npm lifecycle scripts must retain locked, script-free installation and deterministic wheel building.",
);
for (const requiredFile of [
  "bin",
  "npm/vendor",
  "README.md",
  "LICENSE",
  "PRIVACY.md",
  "SECURITY.md",
  "server.json",
]) {
  assert(
    packageJson.files?.includes(requiredFile),
    `package.json files is missing ${requiredFile}.`,
  );
}
assert(
  packageJson.devDependencies?.["@anthropic-ai/mcpb"] === "2.1.2" &&
    packageLock.packages?.["node_modules/@anthropic-ai/mcpb"]?.version ===
      "2.1.2",
  "The MCPB CLI must stay exactly pinned to 2.1.2 in package and lock metadata.",
);
assert(
  packageJson.devDependencies?.fflate === "0.8.3" &&
    packageLock.packages?.["node_modules/fflate"]?.version === "0.8.3",
  "The deterministic ZIP implementation must stay exactly pinned to fflate 0.8.3.",
);
assert(
  packageJson.overrides?.tmp === "0.2.7" &&
    packageLock.packages?.["node_modules/tmp"]?.version === "0.2.7",
  "The MCPB CLI's transitive tmp dependency must stay on patched 0.2.7.",
);
const lockedInstallScripts = Object.entries(packageLock.packages ?? {})
  .filter(([, metadata]) => metadata.hasInstallScript === true)
  .map(
    ([path, metadata]) =>
      `${path.replace(/^node_modules\//, "")}@${metadata.version}`,
  )
  .sort();
assert(
  lockedInstallScripts.length === 0,
  `The lockfile contains an install script: ${lockedInstallScripts.join(", ")}`,
);
const serverApiKeyConfigs = [...packageByRegistry.values()].map((entry) =>
  entry.environmentVariables?.find(
    (variable) => variable.name === "CLOUDCRAFT_API_KEY",
  ),
);
assert(
  serverApiKeyConfigs.every(
    (config) => config?.isRequired === true && config.isSecret === true,
  ),
  "Every MCP Registry package must mark CLOUDCRAFT_API_KEY required and secret.",
);
assert(
  mcpbManifest.manifest_version === "0.4" &&
    mcpbManifest.server?.type === "uv" &&
    mcpbManifest.server?.entry_point ===
      "src/cloudcraft_mcp/__main__.py" &&
    mcpbManifest.server?.mcp_config?.command === "uv",
  "MCPB must use the official v0.4 uv-runtime manifest.",
);
const mcpbApiKey = mcpbManifest.user_config?.cloudcraft_api_key;
const mcpbEnableWrites = mcpbManifest.user_config?.enable_writes;
const mcpbEnableDeletes = mcpbManifest.user_config?.enable_deletes;
const mcpbEnvironment = mcpbManifest.server?.mcp_config?.env ?? {};
assert(
  mcpbApiKey?.type === "string" &&
    mcpbApiKey.required === true &&
    mcpbApiKey.sensitive === true &&
    mcpbApiKey.default === undefined &&
    mcpbManifest.server?.mcp_config?.env?.CLOUDCRAFT_API_KEY ===
      "${user_config.cloudcraft_api_key}",
  "MCPB must receive CLOUDCRAFT_API_KEY only through required sensitive user_config.",
);
assert(
  JSON.stringify(Object.keys(mcpbManifest.user_config ?? {}).sort()) ===
    JSON.stringify([
      "cloudcraft_api_key",
      "enable_deletes",
      "enable_writes",
    ]) &&
    mcpbEnableWrites?.type === "boolean" &&
    mcpbEnableWrites.default === false &&
    mcpbEnableWrites.required !== true &&
    mcpbEnableWrites.sensitive !== true &&
    mcpbEnableDeletes?.type === "boolean" &&
    mcpbEnableDeletes.default === false &&
    mcpbEnableDeletes.required !== true &&
    mcpbEnableDeletes.sensitive !== true &&
    Object.keys(mcpbEnvironment).length === 3 &&
    mcpbEnvironment.CLOUDCRAFT_API_KEY ===
      "${user_config.cloudcraft_api_key}" &&
    mcpbEnvironment.CLOUDCRAFT_ENABLE_WRITES ===
      "${user_config.enable_writes}" &&
    mcpbEnvironment.CLOUDCRAFT_ENABLE_DELETES ===
      "${user_config.enable_deletes}",
  "MCPB mutation safety gates must be optional, non-sensitive booleans disabled by default and mapped directly to the environment.",
);

for (const [registryType, entry] of packageByRegistry) {
  const variables = new Map(
    (entry.environmentVariables ?? []).map((variable) => [
      variable.name,
      variable,
    ]),
  );
  for (const gate of [
    "CLOUDCRAFT_ENABLE_WRITES",
    "CLOUDCRAFT_ENABLE_DELETES",
  ]) {
    const variable = variables.get(gate);
    assert(
      variable?.default === "false" &&
        JSON.stringify(variable.choices) === JSON.stringify(["false", "true"]) &&
        variable.isRequired !== true &&
        variable.isSecret !== true,
      `${registryType} must publish ${gate} as an optional, non-secret, default-off safety gate.`,
    );
  }
}

assert(
  mcpExample.mcpServers?.cloudcraft?.command === "uvx" &&
    JSON.stringify(mcpExample.mcpServers.cloudcraft.args) ===
      JSON.stringify([`cloudcraft-mcp==${packageJson.version}`]) &&
    mcpExample.mcpServers.cloudcraft.env?.CLOUDCRAFT_ENABLE_WRITES ===
      "false" &&
    mcpExample.mcpServers.cloudcraft.env?.CLOUDCRAFT_ENABLE_DELETES ===
      "false",
  "mcp.example.json must run the exactly pinned PyPI package through uvx.",
);
const geminiServer = geminiExtension.mcpServers?.cloudcraft;
const geminiSettings = geminiExtension.settings ?? [];
const geminiEnv = geminiServer?.env ?? {};
const geminiApiKey = geminiExtension.settings?.find(
  (setting) => setting.envVar === "CLOUDCRAFT_API_KEY",
);
assert(
  geminiExtension.name === "cloudcraft-mcp" &&
    geminiServer?.command === "npx" &&
    JSON.stringify(geminiServer.args) ===
      JSON.stringify(["-y", `${packageJson.name}@${packageJson.version}`]),
  "gemini-extension.json must run the exactly pinned npm package.",
);
assert(
  geminiApiKey?.sensitive === true &&
    geminiSettings.filter((setting) => setting.sensitive === true).length ===
      1 &&
    geminiEnv.CLOUDCRAFT_API_KEY === "${CLOUDCRAFT_API_KEY}" &&
    Object.values(geminiEnv).every(
      (value) => typeof value === "string" && value.startsWith("${"),
    ),
  "Gemini must pass the API key through its sole sensitive setting.",
);

const versions = new Map([
  ["package.json", packageJson.version],
  ["package-lock.json", packageLock.version],
  ["pyproject.toml", pythonVersion],
  [
    "Python package",
    capture(
      pythonInit,
      /^__version__\s*=\s*"([^"]+)"/m,
      "Python package",
    ),
  ],
  ["server.json", serverJson.version],
  ["gemini-extension.json", geminiExtension.version],
  ["mcpb/manifest.json", mcpbManifest.version],
  [
    "Dockerfile ARG",
    capture(
      dockerfile,
      /^ARG VERSION=([^\s]+)$/m,
      "Dockerfile ARG VERSION",
    ),
  ],
]);
const uvProjectBlock = uvLock.match(
  /\[\[package\]\]\s+name = "cloudcraft-mcp"\s+version = "([^"]+)"/m,
);
assert(uvProjectBlock?.[1], "uv.lock is missing the cloudcraft-mcp package.");
versions.set("uv.lock", uvProjectBlock[1]);
for (const [index, entry] of (serverJson.packages ?? []).entries()) {
  if (entry.registryType !== "oci") {
    versions.set(`server.json packages[${index}]`, entry.version);
  }
}

const expected = packageJson.version;
const mismatches = [...versions].filter(([, version]) => version !== expected);
if (mismatches.length > 0) {
  throw new Error(
    `Version mismatch; expected ${expected}: ${mismatches
      .map(([label, version]) => `${label}=${String(version)}`)
      .join(", ")}`,
  );
}

function assertDocumentVersions(contents, label) {
  const documentedVersions = [
    ...contents.matchAll(
      /(?:@hypark5540\/cloudcraft-mcp@|cloudcraft-mcp==|cloudcraft-mcp-|ghcr\.io\/hypark5540\/cloudcraft-mcp:|(?:tag|origin|ref=)v)(\d+\.\d+\.\d+)/g,
    ),
  ].map((match) => match[1]);
  assert(
    documentedVersions.length > 0 &&
      documentedVersions.every((version) => version === expected),
    `${label} contains a stale project version: ${[...new Set(documentedVersions)].join(", ")}`,
  );
}

assertDocumentVersions(readme, "README.md");
assertDocumentVersions(releaseGuide, "docs/releasing.md");
assertDocumentVersions(clientGuide, "docs/clients.md");

console.log(`All package and registry metadata match: ${expected}`);
