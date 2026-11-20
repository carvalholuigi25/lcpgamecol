// Bundles every script under public/scripts/<folder>/ into a single minified file,
// public/dist/scripts/all.min.js (with all.min.js.map next to it).
//
//   npm run build-js            build the bundle once
//   npm run build-js -- --watch rebuild the bundle whenever a script changes
//
// The page scripts are classic (non-module) scripts written for different pages: several
// declare the same top-level names (showToast, accountName, ...) and most start their page
// as soon as they run. Concatenating them would fail ("Identifier has already been
// declared") and start every page's code everywhere, so each file is wrapped as a module:
//
//   __lcpDefine("core/sidebar", function (__lcpExpose) { __lcpExpose({ get x() { ... } }); <source> });
//
// A page picks the modules it runs, in order, on the bundle's script tag:
//
//   <script src="/public/dist/scripts/all.min.js" data-modules="core/i18n core/sidebar"></script>
//
// When a module runs, its top-level functions, classes and variables are exposed on
// `window` as live getters/setters, so other scripts and inline handlers keep seeing them
// exactly as they did when every file was loaded with its own <script> tag.
import { readdir, readFile, writeFile, mkdir, rm, rmdir, watch } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { minify } from "terser";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceDir = path.join(root, "public", "scripts");
const outputDir = path.join(root, "public", "dist", "scripts");
const bundleName = "all.min.js";
const bundlePath = path.join(outputDir, bundleName);

const terserOptions = {
  ecma: 2022,
  compress: { passes: 2 },
  mangle: true,
  // The bundle's own top level only holds the loader; module names are function locals.
  toplevel: false,
  format: { comments: false },
};

// Defines the module registry and, at the end of the bundle, runs the modules the page asked for.
const loaderHead = `(() => {
  const factories = new Map();
  window.__lcpDefine = (name, factory) => factories.set(name, factory);
  window.__lcpModules = factories;
})();
`;

const loaderTail = `(() => {
  const factories = window.__lcpModules;
  const script = document.currentScript;
  const wanted = (script && script.dataset.modules || "").split(/\\s+/).filter(Boolean);
  const ran = new Set();
  const expose = (bindings) => {
    for (const name of Object.keys(bindings)) {
      const descriptor = Object.getOwnPropertyDescriptor(bindings, name);
      try {
        Object.defineProperty(window, name, { ...descriptor, enumerable: true, configurable: true });
      } catch (error) {
        console.warn(\`Script global "\${name}" could not be exposed: \${error.message}\`);
      }
    }
  };
  for (const name of wanted) {
    const factory = factories.get(name);
    if (!factory) {
      console.error(\`Unknown script module "\${name}" in \${bundleName}\`);
      continue;
    }
    if (ran.has(name)) continue;
    ran.add(name);
    // Like separate <script> tags: one module failing does not stop the next one.
    try {
      factory.call(window, expose);
    } catch (error) {
      if (typeof window.reportError === "function") window.reportError(error);
      else console.error(error);
    }
  }
})();
`.replace("${bundleName}", bundleName);

async function listScripts(dir) {
  const entries = await readdir(dir, { withFileTypes: true });
  const files = await Promise.all(entries.map((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return listScripts(full);
    return entry.name.endsWith(".js") && !entry.name.endsWith(".min.js") ? [full] : [];
  }));
  return files.flat();
}

function moduleNameOf(source) {
  return path.relative(sourceDir, source).replaceAll("\\", "/").replace(/\.js$/, "");
}

// Names declared at the top level of a script, with whether they can be reassigned.
async function topLevelBindings(code, fileName) {
  const { ast } = await minify(code, { compress: false, mangle: false, format: { ast: true, code: false }, parse: { bare_returns: false } })
    .catch((error) => {
      throw new Error(`${fileName}: ${error.message} (line ${error.line}, col ${error.col})`);
    });
  const bindings = new Map();
  for (const node of ast.body) {
    if (node.TYPE === "Defun" || node.TYPE === "DefClass") {
      bindings.set(node.name.name, true);
    } else if (["Var", "Let", "Const"].includes(node.TYPE)) {
      for (const definition of node.definitions) {
        definition.name.walk({
          _visit(symbol) {
            if (symbol.TYPE?.startsWith("Symbol") && symbol.name) bindings.set(symbol.name, node.TYPE !== "Const");
          },
        });
      }
    }
  }
  return bindings;
}

function exposeCall(bindings) {
  const accessors = [...bindings].map(([name, writable]) => (
    writable
      ? `get ${name}() { return ${name}; }, set ${name}(value) { ${name} = value; }`
      : `get ${name}() { return ${name}; }`
  ));
  return accessors.length ? `__lcpExpose({ ${accessors.join(", ")} });` : "";
}

async function wrapModule(source) {
  const name = moduleNameOf(source);
  const relative = path.relative(root, source).replaceAll("\\", "/");
  const code = await readFile(source, "utf8");
  const bindings = await topLevelBindings(code, relative);
  // The prefix shares the first source line so the source map keeps the original line numbers.
  // Exposing first mirrors classic scripts: functions are hoisted, let/const stay in their TDZ.
  const wrapped = `__lcpDefine(${JSON.stringify(name)}, function (__lcpExpose) { ${exposeCall(bindings)}${code}\n});\n`;
  return { name, relative, code, wrapped };
}

async function removeOldOutputs(dir = outputDir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (error) {
    if (error.code === "ENOENT") return;
    throw error;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      await removeOldOutputs(full);
      await rmdir(full).catch(() => {});
    } else if (full !== bundlePath && full !== `${bundlePath}.map` && /\.min\.js(\.map)?$/.test(entry.name)) {
      await rm(full, { force: true });
    }
  }
}

async function buildBundle() {
  const scripts = (await listScripts(sourceDir)).sort();
  const modules = [];
  let failed = 0;
  for (const source of scripts) {
    try {
      modules.push(await wrapModule(source));
    } catch (error) {
      failed += 1;
      console.error(`Failed to read ${path.relative(root, source)}: ${error.message}`);
    }
  }
  if (failed) {
    process.exitCode = 1;
    console.error(`\n${bundleName} was not rebuilt: ${failed} script(s) could not be parsed.`);
    return false;
  }

  const inputs = { "bundle-loader.js": loaderHead };
  for (const module of modules) inputs[module.relative] = module.wrapped;
  inputs["bundle-runner.js"] = loaderTail;

  const result = await minify(inputs, {
    ...terserOptions,
    sourceMap: { filename: bundleName, url: `${bundleName}.map`, includeSources: true },
  });
  await mkdir(outputDir, { recursive: true });
  await writeFile(bundlePath, result.code);
  await writeFile(`${bundlePath}.map`, result.map);
  await removeOldOutputs();

  const before = modules.reduce((total, module) => total + Buffer.byteLength(module.code), 0);
  const after = Buffer.byteLength(result.code);
  for (const module of modules) console.log(`  ${module.name}`);
  console.log(`\n${modules.length} scripts bundled into ${path.relative(root, bundlePath).replaceAll("\\", "/")}: ${before} -> ${after} bytes (-${Math.round((1 - after / before) * 100)}%).`);
  return true;
}

async function safeBuild() {
  try {
    await buildBundle();
  } catch (error) {
    process.exitCode = 1;
    console.error(`Failed to build ${bundleName}: ${error.message}`);
  }
}

async function watchScripts() {
  console.log(`Watching ${path.relative(root, sourceDir)} for changes...`);
  let timer = null;
  let building = Promise.resolve();
  for await (const { filename } of watch(sourceDir, { recursive: true })) {
    if (!filename?.endsWith(".js")) continue;
    // Editors often write a file several times in a row; rebuild once they settle.
    clearTimeout(timer);
    timer = setTimeout(() => {
      building = building.then(() => {
        process.exitCode = 0;
        return safeBuild();
      });
    }, 150);
  }
}

await safeBuild();
if (process.argv.includes("--watch")) await watchScripts();
