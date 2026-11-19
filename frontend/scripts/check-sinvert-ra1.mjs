import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import ts from "typescript";

const source = await readFile(new URL("../src/sinvert/ra1Presentation.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const { ra1View } = await import(`data:text/javascript;base64,${Buffer.from(code).toString("base64")}`);
const point = (key, value, quality = "valid") => ({ key, raw_value: value, value, quality });
const overview = { diagnostics: { data_freshness: "fresh", communication_state: "online", sinvert_ra1: {} }, telemetry: [
  point("ra1_configured_groups", 5), point("ra1_ready_groups", 1),
  point("ra1_group_1_active_power_raw", 450), point("ra1_group_1_alarm_0", 0x80000001),
  point("ra1_group_1_test_mode", true),
] };
const view = ra1View(overview);
assert.equal(view.fresh, true);
assert.deepEqual(view.groups.map(g => g.configured), [true, false, true, false]);
assert.deepEqual(view.groups.map(g => g.consent), [true, false, false, false]);
assert.equal(view.groups[0].active, 450, "Raw PLC values must not silently become kW");
assert.equal(view.groups[0].test, true);
assert.deepEqual(view.messages.map(m => m.address).sort(), ["DB401.DBX144.7", "DB401.DBX147.0"]);
assert.equal(view.groups[0].complete, false, "Missing alarm words cannot be zeroed");
assert.equal(ra1View(overview, true).fresh, false);
assert.equal(ra1View({ ...overview, diagnostics: { ...overview.diagnostics, data_freshness: "stale" } }).fresh, false);
assert.equal(ra1View(null).groups[0].configured, null);
assert.equal(ra1View({ ...overview, telemetry: [point("ra1_group_1_active_power_raw", 450, "invalid")] }).groups[0].active, null);
console.log("11 RA1 group, raw-value, alarm-address and freshness checks passed; no network calls");
