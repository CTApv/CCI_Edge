// Exercise the actual frontend request wrapper through the local Vite proxy.
// Only lists devices and invokes dry-run endpoints. Never sends PLC commands.
import { readFile, writeFile } from "node:fs/promises";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("../src/api.ts", import.meta.url), "utf8");
const configured = source.replace('import.meta.env.VITE_API_BASE_URL?.trim() || "/api"', '"http://127.0.0.1:5173/api"');
assert.notEqual(configured, source);
const compiled = ts.transpileModule(configured, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
globalThis.window = { setTimeout, clearTimeout };
const fetchReal = globalThis.fetch;
const requests = [];
globalThis.fetch = async (url, init) => {
  const response = await fetchReal(url, init);
  requests.push({ url, method: init?.method ?? "GET", contentType: new Headers(init?.headers).get("Content-Type"), status: response.status });
  return response;
};
const api = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const device = (await api.getDevices()).find(d => d.protocol === "s7_tcp" && d.model.includes("Collaudo"));
assert.ok(device, "No local SINVERT commissioning device configured");
const results = [];
for (const key of ["sinvert_on_request", "sinvert_off_request", "sinvert_power_reference_raw"]) {
  const result = await api.checkSinvertCommand(device.device_id, key, 1);
  assert.equal(result.diagnostics.write_attempted, false);
  assert.equal(result.diagnostics.dry_run, true);
  const request = requests.at(-1);
  assert.equal(request.status, 200);
  assert.equal(request.contentType, "application/json");
  results.push({ command: key, success: result.success, message: result.message, write_attempted: false });
}
const report = { requests, results, plc_commands_sent: false };
await writeFile(new URL("../../../indagine/rapporti/VERIFICA_PREFLIGHT_FRONTEND_20261105.json", import.meta.url), JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
