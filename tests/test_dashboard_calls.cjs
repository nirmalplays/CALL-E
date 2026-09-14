// Smoke-drive the new call-placement render paths against a fuller DOM stub.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

function element(tag) {
  const e = {
    tag, children: [], style: {}, value: '', hidden: true, files: [], _cls: '', textContent: '',
    open: false, disabled: false, dataset: {},
    get className() { return this._cls; },
    set className(v) { this._cls = v; },
    classList: { toggle() {}, add() {}, contains() { return false; } },
    append(...n) { this.children.push(...n); },
    replaceChildren(...n) { this.children = n; },
    add() {}, addEventListener() {}, remove() {}, focus() {},
    reportValidity() { return true; }, showModal() { this.open = true; }, close() { this.open = false; },
  };
  return e;
}
const nodes = new Map();
const ctx = {
  document: {
    getElementById(id) { if (!nodes.has(id)) nodes.set(id, element('div')); return nodes.get(id); },
    createElement: element,
    querySelectorAll() { return []; },
  },
  Option: function () {}, console, Intl, Date, setTimeout, crypto: { randomUUID: () => 'x' },
  confirm: () => false, fetch: () => new Promise(() => {}),
};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), ctx);

function texts(el, out = []) {
  if (el.textContent) out.push(el.textContent);
  (el.children || []).forEach(c => texts(c, out));
  return out;
}

// --- blockerHelp keys must match the backend's live_settings() strings exactly
const backend = JSON.parse(process.argv[3]);
const keys = vm.runInContext('Object.keys(blockerHelp)', ctx);
assert.deepEqual([...keys].sort(), [...backend].sort(),
  'blockerHelp keys drifted from live_settings():\n  js=' + JSON.stringify([...keys].sort()) +
  '\n  py=' + JSON.stringify([...backend].sort()));
console.log('PASS blockerHelp covers every live_settings() blocker');

// --- readiness panel, not ready
vm.runInContext("readiness={configured_for_live:false,blockers:['Live calling disabled','API key missing'],local_budget:0,reserved_calls:0};renderReadiness()", ctx);
assert.equal(nodes.get('live').textContent, 'Calling paused');
assert.equal(nodes.get('readystate').textContent, 'Not ready');
assert.equal(nodes.get('callsused').textContent, '0 / 0');
assert.equal(nodes.get('blockers').children.length, 2);
assert.match(texts(nodes.get('blockers')).join('|'), /CALLE_ENABLE_LIVE_CALLS=true/);
assert.match(texts(nodes.get('blockers')).join('|'), /CALLE_API_KEY/);

// --- readiness panel, ready
vm.runInContext("readiness={configured_for_live:true,blockers:[],local_budget:3,reserved_calls:1};renderReadiness()", ctx);
assert.equal(nodes.get('live').textContent, 'Calling configured');
assert.equal(nodes.get('callsused').textContent, '1 / 3');
assert.equal(nodes.get('blockers').children.length, 1);
console.log('PASS readiness panel renders both states');

// --- configured but out of budget: every dispatch would 403 at reserve time
vm.runInContext("readiness={configured_for_live:true,blockers:[],local_budget:4,reserved_calls:4};renderReadiness()", ctx);
assert.equal(nodes.get('live').textContent, 'Call budget spent');
assert.equal(nodes.get('readystate').textContent, 'Budget spent');
assert.equal(nodes.get('callsused').textContent, '4 / 4');
assert.match(texts(nodes.get('blockers')).join('|'), /CALLE_CALL_BUDGET/);
assert.equal(vm.runInContext('callsAvailable()', ctx), false);
console.log('PASS a spent budget is reported as not callable');

// --- queue rows show dispatch state
vm.runInContext(`records=[
 {call_id:'c1',patient_name:'A',source_id:'s1',status:'pending',dispatch_state:'not_sent',medications:[{name:'m'}]},
 {call_id:'c2',patient_name:'B',source_id:'s2',status:'pending',dispatch_state:'submitted',medications:[{name:'m'}]},
 {call_id:'c3',patient_name:'C',source_id:'s3',status:'pending',dispatch_state:'unknown',medications:[{name:'m'}]}];
$('search').value='';$('filter').value='all';render()`, ctx);
const rowText = texts(nodes.get('records')).join('|');
assert.ok(!/Not dialled/.test(rowText), 'not_sent should stay unlabelled');
assert.match(rowText, /Awaiting outcome/);
assert.match(rowText, /Outcome unknown/);
console.log('PASS queue rows surface dispatch state');

// --- detail dialog: submitted offers reconcile, unknown warns and does not
vm.runInContext("openDetail({call_id:'c2',patient_name:'B',source_id:'s2',status:'pending',dispatch_state:'submitted',medications:[{name:'m',dosage:'d',schedule:[]}],version:1})", ctx);
let body = texts(nodes.get('detailbody')).join('|');
assert.match(body, /Awaiting outcome/);
assert.match(body, /Check outcome with provider/);
assert.ok(!/Place one live call/.test(body), 'a submitted call must not offer a second dispatch');

vm.runInContext("openDetail({call_id:'c3',patient_name:'C',source_id:'s3',status:'pending',dispatch_state:'unknown',provider_failure:{failure_code:'busy',failure_message:'line busy'},medications:[{name:'m',dosage:'d',schedule:[]}],version:1})", ctx);
body = texts(nodes.get('detailbody')).join('|');
assert.match(body, /will not redial/);
assert.match(body, /busy/);
assert.ok(!/Check outcome with provider/.test(body), 'unknown has no provider ID to reconcile against');
assert.ok(!/Place one live call/.test(body), 'unknown must never offer a redial');

vm.runInContext("openDetail({call_id:'c1',patient_name:'A',phone_number:'+10000000000',source_id:'s1',status:'pending',dispatch_state:'not_sent',medications:[{name:'m',dosage:'d',schedule:[]}],version:1})", ctx);
body = texts(nodes.get('detailbody')).join('|');
assert.match(body, /Preview confirmation call/);
console.log('PASS detail dialog gates dispatch, reconcile and redial correctly');

// --- modal errors land inside the dialog, not behind it
nodes.get('detail').open = true;
vm.runInContext("say('boom',true)", ctx);
assert.equal(nodes.get('detailnotice').textContent, 'boom');
assert.equal(nodes.get('detailnotice').hidden, false);
nodes.get('detail').open = false;
vm.runInContext("say('quiet')", ctx);
assert.equal(nodes.get('notice').textContent, 'quiet');
console.log('PASS notices follow the modal');

// --- a queued call with zero dial attempts must be reported as a provider fault
{
  const seen = [];
  const realApi = vm.runInContext('api', ctx);
  ctx.api = async () => ({status: 'active', call_status: 'queued', dial_attempts: 0, submitted_at: '2026-09-14T13:52:18Z'});
  vm.runInContext('api = globalThis.api', ctx);
  nodes.get('detail').open = true;
  vm.runInContext("openDetail({call_id:'c9',patient_name:'D',source_id:'s9',status:'pending',dispatch_state:'submitted',medications:[{name:'m',dosage:'d',schedule:[]}],version:1})", ctx);
  const btn = nodes.get('detailbody').children.filter(n => n.tag === 'button')[0];
  assert.equal(btn.textContent, 'Check outcome with provider');
  return btn.onclick().then(() => {
    const msg = nodes.get('detailnotice').textContent;
    assert.match(msg, /has not attempted to dial even once/);
    assert.match(msg, /provider-side problem/);
    assert.equal(nodes.get('detailnotice').className, 'notice error');
    assert.equal(btn.disabled, false, 'the check stays repeatable');
    nodes.get('detail').open = false;
    vm.runInContext('api = ' + realApi.toString(), ctx);
    console.log('PASS a queued call with no dial attempt is reported as a provider fault');
    rest();
  });
}
function rest() {

// --- reminder jobs: due + ready enables, not due or not ready disables
function jobBtn() {
  return nodes.get('jobs').children.map(r => r.children.filter(c => c.tag === 'button')).flat();
}
vm.runInContext(`patients=[{patient_id:'p1',name:'A'}];
readiness={configured_for_live:true,blockers:[],local_budget:3,reserved_calls:0};
jobs=[{job_id:'j1',patient_id:'p1',kind:'adherence',medication:{name:'m'},due_at:'2000-01-01T00:00:00+00:00',status:'pending',dispatch_state:'not_sent'},
      {job_id:'j2',patient_id:'p1',kind:'adherence',medication:{name:'m'},due_at:'2999-01-01T00:00:00+00:00',status:'pending',dispatch_state:'not_sent'},
      {job_id:'j3',patient_id:'p1',kind:'escalation',medication:{name:'m'},due_at:'2000-01-01T00:00:00+00:00',status:'pending',dispatch_state:'submitted'}];
renderJobs()`, ctx);
let btns = jobBtn();
assert.equal(btns.length, 2, 'only the two not_sent jobs get a button');
assert.equal(btns[0].textContent, 'Place reminder call');
assert.equal(btns[0].disabled, false, 'a due job with calling configured is placeable');
assert.equal(btns[1].textContent, 'Not due yet');
assert.equal(btns[1].disabled, true, 'a future job cannot be dialled');
assert.match(texts(nodes.get('jobs')).join('|'), /Caregiver escalation/);

vm.runInContext("readiness={configured_for_live:false,blockers:['Live calling disabled'],local_budget:0,reserved_calls:0};renderJobs()", ctx);
btns = jobBtn();
assert.equal(btns[0].disabled, true, 'no dispatch while calling is unconfigured');

vm.runInContext("readiness={configured_for_live:true,blockers:[],local_budget:4,reserved_calls:4};renderJobs()", ctx);
btns = jobBtn();
assert.equal(btns[0].disabled, true, 'a due job must not be dispatchable with the budget spent');
console.log('PASS reminder dispatch respects due time, readiness and budget');

console.log('\nAll dashboard smoke checks passed.');
}
