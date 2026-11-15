// Behavioural check for the Timer component (React 18, StrictMode, concurrent root like createRoot).
// usage: node react_check.mjs <Timer.js>   (run with cwd = a folder holding react@18 react-test-renderer@18 esbuild)
// Prints one JSON line: {ok, active_after_mount, seconds_after_3_ticks, active_after_unmount, console, error}
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(path.join(process.cwd(), "package.json"));
const esbuild = require("esbuild");
const React = require("react");

const file = process.argv[2];
const out = { ok: false, active_after_mount: null, seconds_after_3_ticks: null, active_after_unmount: null, console: [], error: null };

const active = new Map();
let nextId = 1;
globalThis.setInterval = (fn) => { const id = nextId++; active.set(id, fn); return id; };
globalThis.clearInterval = (id) => { active.delete(id); };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const log = (...a) => out.console.push(a.map(String).join(" ") + "   Timer.js");
console.log = log;
console.error = () => {};

try {
  const { code } = esbuild.transformSync(readFileSync(file, "utf8"), { loader: "jsx", format: "cjs", jsx: "automatic" });
  const mod = { exports: {} };
  new Function("require", "module", "exports", code)(require, mod, mod.exports);
  const Timer = mod.exports.default;
  const { act, create } = require("react-test-renderer");
  let root;
  act(() => { root = create(React.createElement(React.StrictMode, null, React.createElement(Timer)), { unstable_isConcurrent: true }); });
  out.active_after_mount = active.size;
  for (let i = 0; i < 3; i++) act(() => { for (const fn of [...active.values()]) fn(); });
  const text = JSON.stringify(root.toJSON());
  const m = text.match(/Seconds: ","?(\d+)/) || text.match(/(\d+)/);
  out.seconds_after_3_ticks = m ? Number(m[1]) : null;
  act(() => root.unmount());
  out.active_after_unmount = active.size;
  out.ok = out.active_after_mount === 1 && out.seconds_after_3_ticks === 3 && out.active_after_unmount === 0;
} catch (e) {
  out.error = `${e.name}: ${e.message}`;
}
process.stdout.write(JSON.stringify(out) + "\n");
