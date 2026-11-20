// Minifies every script under public/scripts/<folder>/ into public/dist/scripts/<folder>/<name>.min.js
// (with a source map next to it), keeping the folder layout.
//
//   npm run build-js            minify everything once
//   npm run build-js -- --watch re-minify a file whenever it changes
//
// The page scripts are classic (non-module) scripts that share globals across files, so
// top-level names are left alone (toplevel: false); only local names are mangled.
import { readdir, readFile, writeFile, mkdir, rm, watch } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { minify } from "terser";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = path.join(root, "public", "scripts");
const outputDir = path.join(root, "public", "dist", "scripts");

const terserOptions = {
  ecma: 2022,
  compress: { passes: 2 },
  mangle: true,
  toplevel: false,
  format: { comments: false },
};

async function listScripts(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = await Promise.all(entries.map((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return listScripts(full);
    return entry.name.endsWith(".js") && !entry.name.endsWith(".min.js") ? [full] : [];
  }));
  return files.flat();
}

function outputPathOf(source) {
  const relative = path.relative(sourceDir, source);
  return path.join(outputDir, relative.replace(/\.js$/, ".min.js"));
}

async function minifyFile(source) {
  const target = outputPathOf(source);
  const mapName = `${path.basename(target)}.map`;
  const code = await readFile(source, "utf8");
  const result = await minify({ [path.relative(root, source).replaceAll("\\", "/")]: code }, {
    ...terserOptions,
    sourceMap: { filename: path.basename(target), url: mapName },
  });
  await mkdir(path.dirname(target), { recursive: true });
  await writeFile(target, result.code);
  await writeFile(`${target}.map`, result.map);
  return { source, before: Buffer.byteLength(code), after: Buffer.byteLength(result.code) };
}

function report({ source, before, after }) {
  const name = path.relative(sourceDir, source).replaceAll("\\", "/");
  const saved = before ? Math.round((1 - after / before) * 100) : 0;
  console.log(`${name.padEnd(36)} ${String(before).padStart(8)} -> ${String(after).padStart(8)} bytes (-${saved}%)`);
}

// Removes minified files whose source no longer exists. The output folder is never wiped
// as a whole, so a watcher and a one-off build can run side by side (npm run startw*).
async function removeStaleOutputs(scripts) {
  const expected = new Set(scripts.map(outputPathOf));
  let outputs = [];
  try {
    outputs = (await readdir(outputDir, { recursive: true })).map((name) => path.join(outputDir, name));
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  for (const output of outputs) {
    const minified = output.endsWith(".min.js.map") ? output.slice(0, -4) : output;
    if (minified.endsWith(".min.js") && !expected.has(minified)) await rm(output, { force: true });
  }
}

async function buildAll() {
  const scripts = await listScripts(sourceDir);
  await removeStaleOutputs(scripts);
  let failed = 0;
  let before = 0;
  let after = 0;
  for (const source of scripts.sort()) {
    try {
      const result = await minifyFile(source);
      report(result);
      before += result.before;
      after += result.after;
    } catch (error) {
      failed += 1;
      console.error(`Failed to minify ${path.relative(root, source)}: ${error.message}`);
    }
  }
  console.log(`\n${scripts.length - failed}/${scripts.length} scripts minified: ${before} -> ${after} bytes.`);
  if (failed) process.exitCode = 1;
}

async function watchScripts() {
  console.log(`Watching ${path.relative(root, sourceDir)} for changes...`);
  for await (const { filename } of watch(sourceDir, { recursive: true })) {
    if (!filename?.endsWith(".js")) continue;
    const source = path.join(sourceDir, filename);
    try {
      report(await minifyFile(source));
    } catch (error) {
      if (error.code !== "ENOENT") console.error(`Failed to minify ${filename}: ${error.message}`);
    }
  }
}

await buildAll();
if (process.argv.includes("--watch")) await watchScripts();
