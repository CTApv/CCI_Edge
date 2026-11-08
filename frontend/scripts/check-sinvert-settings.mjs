// Round-trip the existing limit through the real UI API helper and local proxy.
// Does not select a new positive limit and never calls PLC command endpoints.
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
  assert.ok(!url.includes("/commands/") && !url.includes("/preflight/"));
  const response = await fetchReal(url, init);
  requests.push({ url, method: init?.method ?? "GET", status: response.status,
    payload: init?.body ? JSON.parse(init.body) : null });
  return response;
};
const api = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`);
const device = (await api.getDevices()).find(d => d.protocol === "s7_tcp" && d.model.includes("Collaudo"));
assert.ok(device);
const maximum = Number(device.connection_settings.sinvert_reference_max_raw ?? 0);
const updated = await api.saveSinvertReferenceLimit(device.device_id, maximum);
const write = requests.find(r => r.method === "PUT");
assert.equal(write.status, 200);
assert.ok(!("device_id" in write.payload));
assert.ok(!("created_at" in write.payload));
assert.deepEqual(write.payload.profile_overrides, device.profile_overrides);
assert.deepEqual(updated.connection_settings, device.connection_settings);
assert.equal(updated.device_id, device.device_id);
const report = { requests, same_limit_round_trip: true, maximum, plc_commands_sent: false };
await writeFile(new URL("../../../indagine/rapporti/VERIFICA_SALVATAGGIO_LIMITE_FRONTEND_20261105.json", import.meta.url), JSON.stringify(report, null, 2));
console.log(JSON.stringify({ status: write.status, maximum, same_limit_round_trip: true, unexpected_fields: false, plc_commands_sent: false }));
