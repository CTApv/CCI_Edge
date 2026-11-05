// Verify the real frontend helper with a mocked configuration API. No network.
import { readFile } from "node:fs/promises";
import assert from "node:assert/strict";
import ts from "typescript";
const source=await readFile(new URL('../src/api.ts',import.meta.url),'utf8');
const code=ts.transpileModule(source.replace('import.meta.env.VITE_API_BASE_URL?.trim() || "/api"','"/api"'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText;
globalThis.window={setTimeout,clearTimeout};
let device={device_id:'local-test',created_at:'2026-01-01T00:00:00Z',name:'PLC',brand:'SINVERT',model:'M/TL S7-300 - Collaudo comandi',protocol:'s7_tcp',transport:'tcp',status:'online',connection_settings:{host:'192.0.2.1',port:102,sinvert_write_mode:'read_only',sinvert_reference_max_raw:1000},profile_overrides:{example:'preserved'}};
const requests=[];
globalThis.fetch=async (url,init)=>{
  assert.equal(url,'/api/devices/local-test');
  requests.push({method:init?.method??'GET',body:init?.body?JSON.parse(init.body):null});
  if(init?.method==='PUT') {
    const payload=JSON.parse(init.body);
    assert.deepEqual(Object.keys(payload).sort(),['name','brand','model','protocol','transport','status','profile_overrides','connection_settings'].sort());
    assert.equal(new Headers(init.headers).get('Content-Type'),'application/json');
    device={...device,...payload};
  }
  return new Response(JSON.stringify(device),{status:200,headers:{'Content-Type':'application/json'}});
};
const api=await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const enabled=await api.saveSinvertCommissioningMode('local-test',true);
assert.equal(enabled.connection_settings.sinvert_write_mode,'commissioning');
assert.equal(enabled.connection_settings.sinvert_reference_max_raw,1000);
assert.equal(enabled.connection_settings.host,'192.0.2.1');
assert.deepEqual(enabled.profile_overrides,{example:'preserved'});
const disabled=await api.saveSinvertCommissioningMode('local-test',false);
assert.equal(disabled.connection_settings.sinvert_write_mode,'read_only');
const count=requests.length;
await assert.rejects(()=>api.saveSinvertCommissioningMode('local-test','true'));
assert.equal(requests.length,count);
device.model='M/TL S7-300 - Diagnostica';
await assert.rejects(()=>api.saveSinvertCommissioningMode('local-test',true));
assert.equal(requests.filter(r=>r.method==='PUT').length,2);
console.log('SINVERT profile enable/disable payload checks passed; all API calls mocked, no PLC writes');
