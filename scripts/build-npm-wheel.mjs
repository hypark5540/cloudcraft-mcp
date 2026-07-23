import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packageJson = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const pyproject = await readFile(resolve(root, "pyproject.toml"), "utf8");

function capture(pattern, label) {
  const match = pyproject.match(pattern);
  if (!match?.[1]) throw new Error(`Could not read ${label} from pyproject.toml.`);
  return match[1];
}

const pythonProject = capture(/^name\s*=\s*"([^"]+)"/m, "project name");
const pythonVersion = capture(/^version\s*=\s*"([^"]+)"/m, "version");
if (pythonVersion !== packageJson.version) {
  throw new Error(
    `Python version ${pythonVersion} does not match npm version ${packageJson.version}.`,
  );
}

const wheelDistribution = pythonProject.replace(/[-.]+/g, "_");
const wheelName = `${wheelDistribution}-${packageJson.version}-py3-none-any.whl`;
const vendorDirectory = resolve(root, "npm/vendor");
const output = resolve(vendorDirectory, wheelName);
const temporaryOutput = `${output}.${process.pid}.tmp`;
const uv = process.env.CLOUDCRAFT_MCP_UV || "uv";

function runUv(args) {
  return new Promise((resolvePromise, reject) => {
    const child = spawn(uv, args, {
      cwd: root,
      env: {
        ...process.env,
        // Hatchling honors this timestamp when writing ZIP members.
        SOURCE_DATE_EPOCH: "946684800",
      },
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
          `${uv} ${args.join(" ")} failed (${signal ?? `code ${String(code)}`}).`,
        ),
      );
    });
  });
}

async function buildWheel(outputDirectory) {
  await mkdir(outputDirectory, { recursive: true });
  await runUv([
    "build",
    "--wheel",
    "--no-sources",
    "--out-dir",
    outputDirectory,
  ]);
  const wheels = (await readdir(outputDirectory))
    .filter((entry) => entry.endsWith(".whl"))
    .sort();
  if (wheels.length !== 1 || wheels[0] !== wheelName) {
    throw new Error(
      `Unexpected wheel output: ${wheels.join(", ") || "none"}; expected ${wheelName}.`,
    );
  }
  return readFile(resolve(outputDirectory, wheels[0]));
}

function sha256(contents) {
  return createHash("sha256").update(contents).digest("hex");
}

const temporaryRoot = await mkdtemp(resolve(tmpdir(), "cloudcraft-mcp-wheel-"));
try {
  const first = await buildWheel(resolve(temporaryRoot, "first"));
  const second = await buildWheel(resolve(temporaryRoot, "second"));
  if (!first.equals(second)) {
    throw new Error(
      `Wheel builds are not deterministic: ${sha256(first)} != ${sha256(second)}.`,
    );
  }

  await mkdir(vendorDirectory, { recursive: true });
  for (const entry of await readdir(vendorDirectory, { withFileTypes: true })) {
    if (!/^cloudcraft_mcp-.*\.whl$/.test(entry.name)) continue;
    if (!entry.isFile()) {
      throw new Error(`Refusing to replace non-file wheel entry: ${entry.name}`);
    }
    await rm(resolve(vendorDirectory, entry.name), { force: true });
  }

  await writeFile(temporaryOutput, first, { mode: 0o644 });
  await rename(temporaryOutput, output);
  await chmod(output, 0o644);
  console.log(
    `Deterministic npm wheel written: ${relative(root, output)} (sha256 ${sha256(first)})`,
  );
} finally {
  await rm(temporaryOutput, { force: true });
  await rm(temporaryRoot, { recursive: true, force: true });
}
