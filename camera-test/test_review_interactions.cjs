const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const CaptureFlow=require('./web/capture-flow.js');
const source=fs.readFileSync(path.join(__dirname,'web/app.js'),'utf8');
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a);assert.ok(a>=0&&b>a);return source.slice(a,b);}
const assignSource=section('async function assignBrand(',"$('batchBrandForm').onsubmit");
const reviewSource=section('async function reviewProducts(',"$('reviewBeforeSave').onclick");
function ui(options={}){
 const elements=new Map(),calls=[];
 const get=id=>{if(!elements.has(id))elements.set(id,{value:id==='batchBrand'?'NIKE':'',disabled:false,open:false,shows:0,showModal(){this.open=true;this.shows++;},close(){this.open=false;}});return elements.get(id);};
 const ctx={busy:false,step:options.step??3,selectedGroups:new Set(['g1']),CaptureFlow,$:get,
  state:{work_id:'work1',groups:[{id:'g1',brand:'NIKE',reviewed:false,photos:[{excluded:false}]}]},
  renderBrandSelection(){},document:{querySelector(){return{scrollIntoView(){}};}}};
 ctx.act=async payload=>{calls.push(payload);if(options.ok!==false&&payload.action==='review_groups')ctx.state.groups.forEach(g=>{if(payload.groups.includes(g.id))g.reviewed=true;});if(options.afterAct)options.afterAct(ctx);return options.ok!==false;};
 ctx.goStep=async next=>{ctx.step=next;};
 vm.createContext(ctx);vm.runInContext(assignSource+reviewSource,ctx);
 return{ctx,get,calls};
}
test('successful brand assignment or clearing resets selection and input',async()=>{
 for(const brand of ['NIKE','']){
  const {ctx,get}=ui();ctx.selectedGroups.add('g2');
  await ctx.assignBrand(brand);
  assert.equal(ctx.selectedGroups.size,0);assert.equal(get('batchBrand').value,'');
 }
});
test('failed brand assignment keeps selection and input for retry',async()=>{
 const {ctx,get}=ui({ok:false});await ctx.assignBrand('NIKE');
 assert.deepEqual([...ctx.selectedGroups],['g1']);assert.equal(get('batchBrand').value,'NIKE');
});
test('review all asks after success; no keeps the page and reviewed state',async()=>{
 const {ctx,get,calls}=ui();await get('reviewAll').onclick();
 assert.equal(get('reviewNextDialog').open,true);assert.equal(ctx.step,3);assert.equal(ctx.state.groups[0].reviewed,true);
 get('stayAfterReview').onclick();
 assert.equal(get('reviewNextDialog').open,false);assert.equal(ctx.step,3);assert.equal(ctx.state.groups[0].reviewed,true);assert.equal(calls.length,1);
});
test('yes opens the save page without saving files or repeating review',async()=>{
 const {ctx,get,calls}=ui();await get('reviewAll').onclick();await get('saveAfterReview').onclick();
 assert.equal(get('reviewNextDialog').open,false);assert.equal(ctx.step,4);assert.equal(ctx.state.groups[0].reviewed,true);
 assert.equal(calls.length,1);assert.equal(calls[0].action,'review_groups');
});
test('review failure, no targets, busy state, save page or changed work/page never prompts',async()=>{
 for(const options of [{ok:false},{step:4},{afterAct:ctx=>{ctx.state.work_id='work2';}},{afterAct:ctx=>{ctx.step=1;}},{noTargets:true},{busy:true}]){
  const {ctx,get}=ui(options);if(options.noTargets)ctx.state.groups[0].brand='';if(options.busy)ctx.busy=true;
  await get('reviewAll').onclick();assert.equal(get('reviewNextDialog').shows,0,JSON.stringify(options));
 }
 const {ctx,get}=ui();assert.equal(await ctx.reviewProducts(['g1']),true);assert.equal(get('reviewNextDialog').shows,0);
});
