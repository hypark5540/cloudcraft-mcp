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
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const project = JSON.parse(
  await readFile(resolve(root, "package.json"), "utf8"),
);
const bootstrapVersion = "0.0.0";
const archiveName = `${project.name
  .replace(/^@/, "")
  .replaceAll("/", "-")}-${bootstrapVersion}.tgz`;
const outputDirectory = resolve(root, "release-artifacts/npm-bootstrap");
const output = resolve(outputDirectory, archiveName);
const temporaryOutput = `${output}.${process.pid}.tmp`;

function runNpm(args, cwd) {
  return new Promise((resolvePromise, reject) => {
    const npmCli = process.env.npm_execpath;
    const command = npmCli ? process.execPath : "npm";
    const commandArgs = npmCli ? [npmCli, ...args] : args;
    const child = spawn(command, commandArgs, {
      cwd,
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
          `npm ${args.join(" ")} failed (${signal ?? `code ${String(code)}`}).`,
        ),
      );
    });
  });
}

const temporaryRoot = await mkdtemp(
  resolve(tmpdir(), "cloudcraft-mcp-npm-bootstrap-"),
);
const stage = resolve(temporaryRoot, "package");
const first = resolve(temporaryRoot, "first");
const second = resolve(temporaryRoot, "second");

try {
  await mkdir(stage, { recursive: true });
  await mkdir(first);
  await mkdir(second);

  const metadata = {
    name: project.name,
    version: bootstrapVersion,
    description:
      `Bootstrap marker for Cloudcraft MCP trusted publishing; install version ${project.version} or later`,
    author: project.author,
    license: project.license,
    repository: project.repository,
    homepage: project.homepage,
    bugs: project.bugs,
    publishConfig: { access: "public", tag: "bootstrap" },
    engines: project.engines,
    files: ["README.md", "LICENSE"],
  };
  await writeFile(
    resolve(stage, "package.json"),
    `${JSON.stringify(metadata, null, 2)}\n`,
    "utf8",
  );
  await writeFile(
    resolve(stage, "README.md"),
    [
      "# Cloudcraft MCP npm bootstrap",
      "",
      "This inert 0.0.0 package exists only to establish npm Trusted Publishing.",
      `Install ${project.name}@${project.version} or a later released version.`,
      "",
    ].join("\n"),
    "utf8",
  );
  await copyFile(resolve(root, "LICENSE"), resolve(stage, "LICENSE"));

  await runNpm(["pack", "--pack-destination", first], stage);
  await runNpm(["pack", "--pack-destination", second], stage);
  const [firstArchive, secondArchive] = await Promise.all([
    readFile(resolve(first, archiveName)),
    readFile(resolve(second, archiveName)),
  ]);
  if (!firstArchive.equals(secondArchive)) {
    throw new Error("npm bootstrap tarball is not reproducible.");
  }

  await mkdir(outputDirectory, { recursive: true });
  await writeFile(temporaryOutput, firstArchive, { mode: 0o644 });
  await rename(temporaryOutput, output);
  await chmod(output, 0o644);
  const digest = createHash("sha256").update(firstArchive).digest("hex");
  console.log(`Deterministic npm bootstrap written: ${output}`);
  console.log(`sha256 ${digest}`);
} finally {
  await rm(temporaryOutput, { force: true });
  await rm(temporaryRoot, { recursive: true, force: true });
}
