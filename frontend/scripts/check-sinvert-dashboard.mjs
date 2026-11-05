// Headless visual and interaction checks against the actual local dashboard.
// Blocks command endpoints and never submits a PLC command or edits settings.
import { spawn } from "node:child_process";
import { readFile, writeFile, mkdir, mkdtemp } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import assert from "node:assert/strict";
import WebSocket from "ws";

const artifacts = new URL("../../../indagine/rapporti/dashboard_sinvert/", import.meta.url);
await mkdir(artifacts, { recursive: true });
const audit = new URL("../../local_runtime/sinvert_command_audit.jsonl", import.meta.url);
async function auditHash() { try { return createHash("sha256").update(await readFile(audit)).digest("hex"); } catch (e) { if (e.code === "ENOENT") return null; throw e; } }
const before = await auditHash();
const profile = await mkdtemp(join(tmpdir(), "sinvert-preview-chrome-"));
const browser = spawn("C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe", [
  "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
  "--remote-debugging-port=0", `--user-data-dir=${profile}`, "about:blank",
], { windowsHide: true, stdio: ["ignore", "ignore", "pipe"] });
let socket; const errors=[]; const requests=[]; const checks=[];
try {
  const browserUrl = await new Promise((resolve,reject) => {
    const timer=setTimeout(() => reject(new Error("Chrome debugging endpoint timeout")),15000);
    let output="";
    browser.stderr.on("data", chunk => { output+=String(chunk); const match=output.match(/DevTools listening on (ws:\/\/[^\s]+)/); if (match) { clearTimeout(timer); resolve(match[1]); } });
    browser.on("error",reject);
  });
  const port=new URL(browserUrl).port;
  const targets=await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  socket=new WebSocket(targets.find(t => t.type==="page").webSocketDebuggerUrl);
  await new Promise((resolve,reject) => { socket.once("open",resolve);socket.once("error",reject); });
  let seq=0;const pending=new Map();
  socket.on("message", raw => {
    const message=JSON.parse(String(raw));
    if (message.id) { const promise=pending.get(message.id);if (!promise)return;pending.delete(message.id);message.error?promise.reject(new Error(JSON.stringify(message.error))):promise.resolve(message.result); }
    if (message.method==="Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text+" "+(message.params.exceptionDetails.exception?.description??""));
    if (message.method==="Network.requestWillBeSent") requests.push({url:message.params.request.url,method:message.params.request.method});
  });
  function cdp(method,params={}) { return new Promise((resolve,reject) => {const id=++seq;pending.set(id,{resolve,reject});socket.send(JSON.stringify({id,method,params}));}); }
  async function evaluate(expression) {
    const result=await cdp("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true,userGesture:true});
    if (result.exceptionDetails)throw new Error(result.exceptionDetails.exception?.description??result.exceptionDetails.text);
    return result.result?.value;
  }
  async function wait(expression) {
    const deadline=Date.now()+18000;
    while(Date.now()<deadline) { if(await evaluate(expression))return;await new Promise(resolve=>setTimeout(resolve,200)); }
    throw new Error("Timed out: "+expression);
  }
  async function capture(name) {
    await evaluate("window.scrollTo(0,0)");
    const result=await cdp("Page.captureScreenshot",{format:"png",captureBeyondViewport:false});
    await writeFile(new URL(name,artifacts),Buffer.from(result.data,"base64"));
  }
  async function tab(text, mobile=false) {
    await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(mobile?".sv-mobile-nav button":".sv-sidebar nav button")})).find(b=>b.textContent.includes(${JSON.stringify(text)})).click()`);
  }
  await cdp("Runtime.enable");await cdp("Network.enable");await cdp("Page.enable");
  await cdp("Network.setBlockedURLs",{urls:["*/commands/*"]});
  await cdp("Emulation.setDeviceMetricsOverride",{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp("Page.navigate",{url:"http://127.0.0.1:5173/sinvert.html"});
  await wait("document.querySelectorAll('.sv-inverter').length===4");
  assert.equal(await evaluate("Array.from(document.querySelectorAll('.sv-control-column .sv-button--full')).every(b=>b.disabled)"),true);
  checks.push("Default consultazione: both collective command buttons disabled");
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  await capture("01_panoramica_desktop.png");
  await tab("Allarmi");await wait("!!document.querySelector('.sv-table-tools')");
  const initial=await evaluate("document.querySelectorAll('tbody tr').length");
  await evaluate("Array.from(document.querySelectorAll('.sv-segmented button')).find(b=>b.textContent==='Allarmi').click()");
  assert.ok(await evaluate("document.querySelectorAll('tbody tr').length")<=initial);
  checks.push("Alarm filtering works without changing PLC state");
  await capture("02_allarmi_desktop.png");
  await tab("Collaudo");
  assert.equal(await evaluate("document.querySelector('.sv-toggle input').checked"),false);
  await capture("03_collaudo_desktop.png");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Verifica arresto senza inviare')).click()");
  await wait("!!document.querySelector('.sv-outcome') && !document.querySelector('.sv-working')");
  assert.equal(await evaluate("document.querySelector('.sv-outcome').textContent.includes('Controlli superati')"),true);
  checks.push("Real OFF preflight succeeds and identifies operation as read-only");
  await evaluate("document.querySelector('.sv-toggle input').click()");
  await evaluate("Array.from(document.querySelectorAll('button')).find(b=>b.textContent.includes('Prepara arresto')).click()");
  await wait("!!document.querySelector('[role=dialog]')");
  assert.equal(await evaluate("document.querySelector('[role=dialog]').textContent.includes('tutte le posizioni')"),true);
  await capture("04_riepilogo_richiesta.png");
  await cdp("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await cdp("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await wait("!document.querySelector('[role=dialog]')");
  checks.push("Command review states collective scope; Escape cancels; no send performed");
  await tab("Diagnostica");await capture("05_diagnostica_desktop.png");
  await cdp("Page.reload");await wait("document.querySelectorAll('.sv-inverter').length===4");
  await tab("Collaudo");
  assert.equal(await evaluate("document.querySelector('.sv-toggle input').checked"),false);
  checks.push("Reload resets manual activation");
  await cdp("Emulation.setDeviceMetricsOverride",{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await tab("Panoramica",true);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  await capture("06_panoramica_mobile.png");
  await tab("Collaudo",true);
  assert.equal(await evaluate("document.documentElement.scrollWidth<=window.innerWidth"),true);
  await capture("07_collaudo_mobile.png");
  checks.push("390px mobile: navigation available, overview and commissioning have no horizontal overflow");
  await cdp("Network.setBlockedURLs",{urls:["*/commands/*","*127.0.0.1:5173/api/*"]});
  await cdp("Emulation.setDeviceMetricsOverride",{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
  await cdp("Page.reload");
  await wait("!!document.querySelector('.sv-notice--bad')");
  assert.equal(await evaluate("document.querySelector('.sv-live').textContent.includes('verificare')"),true);
  await capture("08_backend_non_disponibile.png");
  checks.push("Backend unreachable: explicit error, no fabricated online state or measurements");
  assert.equal(errors.length,0,JSON.stringify(errors));
  assert.equal(requests.filter(request=>request.url.includes("/commands/")).length,0);
  assert.equal(before,await auditHash(),"PLC command audit changed during UI checks");
  await writeFile(new URL("checks.json",artifacts),JSON.stringify({checks,runtime_errors:errors,command_requests:0,command_audit_unchanged:true,requests:requests.filter(request=>request.url.includes('/api/')),profile,plc_commands_sent:false},null,2));
  console.log(JSON.stringify({checks:checks.length,runtime_errors:errors.length,command_requests:0,artifacts:fileURLToPath(artifacts)}));
  await cdp("Browser.close").catch(()=>{});
} finally { socket?.close();browser.kill(); }
