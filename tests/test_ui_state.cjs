// Logic regression: a late response must not expose data after workspace lock.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
function element(){return {children:[],style:{},value:'',hidden:true,files:[],classList:{toggle(){}},append(n){this.children.push(n);},replaceChildren(...n){this.children=n;},add(){},addEventListener(){},reportValidity(){return true;}};}
const nodes=new Map();
const ctx={document:{getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id);},createElement:element,querySelectorAll(){return [];}},Option:function(){},console,Intl,Date,setTimeout,confirm:()=>true};
let resolveFetch;
ctx.fetch=()=>new Promise(r=>{resolveFetch=r;});
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),ctx);
(async()=>{
  const pending=vm.runInContext("token='old-session'; api('patients')",ctx);
  vm.runInContext("token=''",ctx);
  resolveFetch({ok:true,json:async()=>[{name:'private'}]});
  await assert.rejects(pending,/session changed/);
  nodes.get('ocrfile').files=[{size:10}];
  const upload=vm.runInContext("token='old-session'; $('extractocr').onclick()",ctx);
  vm.runInContext("token=''; clearOCR()",ctx);
  resolveFetch({ok:true,json:async()=>({scan_id:'secret',text:'private',draft_medications:[]})});
  await upload;
  assert.equal(nodes.get('ocrtext').textContent,'');
  assert.equal(nodes.get('ocrresult').hidden,true);
  console.log('PASS late API and OCR responses do not restore locked data');
})().catch(e=>{console.error(e);process.exitCode=1;});
