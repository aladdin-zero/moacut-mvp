const $=id=>document.getElementById(id);
let state,step=1,roi=[.05,.05,.95,.95],roiInitialized=false,drag=null,selecting=false;
let busy=false,polling=false,streaming=false,lastSignature='',audio;
let tracker=new CaptureFlow.CaptureTracker(),guide=new CaptureFlow.GuideProgress();
const selectedGroups=new Set();let brandOptionsSignature='';
let voiceAudio=new Audio(),voiceToken=0,successTimer,flashTimer,lastGuideSignature='',guideDirty=false,destinationDirty=false;
const labels={shirt:'상의',trousers:'바지',coat:'코트',dress:'드레스',skirt:'스커트',shoe:'신발',handbag:'가방','folded garment':'접은 옷'};
function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
async function post(path,body={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();if(!r.ok)throw Error(data.error||'작업에 실패했습니다.');return data;}
async function submit(path,body,notice){busy=true;try{state=await post(path,body);render();if(notice)message(notice);return true;}catch(e){message(e.message,true);return false;}finally{busy=false;render();}}
const act=(body,notice)=>submit('/api/action',body,notice);
async function photoAction(action,group,file){if(await act({action,group,file},action==='delete_photo'?'사진을 휴지통으로 삭제했습니다. 사진 확인 아래에서 복원할 수 있습니다.':'사진을 복원했습니다. 묶음을 다시 검토해 주세요.')){guide.positions.delete(group);lastGuideSignature='';renderGuide();}}
function button(text,handler){const b=document.createElement('button');b.textContent=text;b.onclick=handler;return b;}
async function goStep(next){if(next!==2&&state?.automatic)await act({action:'automatic',enabled:false});step=next;document.body.classList.toggle('capture-mode',step===2);if(step!==2){voiceToken++;voiceAudio.pause();}document.querySelectorAll('[data-panel]').forEach(el=>el.hidden=Number(el.dataset.panel)!==step);document.querySelectorAll('[data-step]').forEach(el=>{el.classList.toggle('selected',Number(el.dataset.step)===step);el.setAttribute('aria-current',Number(el.dataset.step)===step?'step':'false');});render();overlay();}
document.querySelectorAll('[data-step]').forEach(b=>b.onclick=()=>goStep(Number(b.dataset.step)));
$('toCamera').onclick=()=>goStep(2);$('toReview').onclick=()=>goStep(3);$('toSave').onclick=()=>goStep(4);
function audioPrefs(){try{return JSON.parse(localStorage.getItem('b-one-audio-v1'))||{};}catch{return {};}}
const preferences=audioPrefs();$('sound').checked=preferences.sound!==false;$('voice').checked=preferences.voice!==false;$('volume').value=Number.isFinite(preferences.volume)?Math.max(0,Math.min(100,preferences.volume)):85;
function saveAudioPrefs(){const settings={sound:$('sound').checked,voice:$('voice').checked,volume:Number($('volume').value)};$('volumeValue').textContent=settings.volume+'%';voiceAudio.volume=settings.volume/100;try{localStorage.setItem('b-one-audio-v1',JSON.stringify(settings));}catch{}if(!settings.voice){voiceToken++;voiceAudio.pause();}}
['sound','voice','volume'].forEach(id=>$(id).oninput=saveAudioPrefs);saveAudioPrefs();
async function unlockAudio(){try{audio ||= new AudioContext();await audio.resume();}catch{$('audioStatus').textContent='촬영음 재생을 준비하지 못했습니다. 화면 알림은 계속 표시합니다.';}}
function beep(){if(!$('sound').checked||!audio)return;const volume=Number($('volume').value)/100;if(!volume)return;try{audio.resume();for(let i=0;i<2;i++){const tone=audio.createOscillator(),gain=audio.createGain(),start=audio.currentTime+i*.13;tone.connect(gain);gain.connect(audio.destination);gain.gain.setValueAtTime(.001,start);gain.gain.exponentialRampToValueAtTime(.55*volume,start+.015);gain.gain.exponentialRampToValueAtTime(.001,start+.12);tone.frequency.value=i?1320:980;tone.start(start);tone.stop(start+.125);}}catch{}}
function voiceUrl(text){return '/api/voice?text='+encodeURIComponent(text);}
async function speak(text,delay=0){const token=++voiceToken;voiceAudio.pause();if(!$('voice').checked||Number($('volume').value)===0)return;if(delay)await new Promise(resolve=>setTimeout(resolve,delay));if(token!==voiceToken)return;voiceAudio.src=voiceUrl(text);voiceAudio.volume=Number($('volume').value)/100;try{await voiceAudio.play();$('audioStatus').textContent='이 PC의 음성으로 안내합니다.';}catch{if(token===voiceToken)$('audioStatus').textContent='음성을 재생하지 못했습니다. 소리 확인을 눌러 주세요. 촬영음과 화면 알림은 계속 사용할 수 있습니다.';}}
voiceAudio.addEventListener('error',()=>{$('audioStatus').textContent='음성 안내를 준비하지 못했습니다. 소리 확인을 다시 눌러 주세요.';});
$('soundTest').onclick=async()=>{await unlockAudio();beep();await speak('촬영됐습니다. 소리와 음성 안내를 확인해 주세요.',260);};
let warmedGuide='';async function warmVoice(steps){const signature=JSON.stringify(steps);if(signature===warmedGuide)return;warmedGuide=signature;const texts=['촬영됐습니다.','자동 촬영을 시작합니다.','4컷 촬영 완료. 다음 상품을 놓아 주세요.',...steps.flatMap(t=>[t,'촬영됐습니다. 다음 안내. '+t])];for(const text of texts){if(warmedGuide!==signature)return;try{await fetch(voiceUrl(text));}catch{}}}
function activeGroup(){return state?.groups.find(g=>g.id===state.active_group)||null;}
function guideText(){return guide.next(activeGroup());}
function readGuide(){speak(guideText()||'설정한 촬영 안내가 없습니다. 필요한 사진을 자유롭게 촬영하세요.');}
function chooseGuide(index){guide.choose(activeGroup(),index);lastGuideSignature='';renderGuide();readGuide();}
$('previousGuide').onclick=()=>chooseGuide(guide.index(activeGroup())-1);$('nextGuide').onclick=()=>chooseGuide(guide.index(activeGroup())+1);$('repeatGuide').onclick=async()=>{await unlockAudio();readGuide();};
const shotOptions=['앞면 전체','뒷면 전체','측면','브랜드 라벨','사이즈 라벨','소재·세탁 라벨','특징·상태 상세'];
let editorSignature=null;
function addGuideRow(value=''){
 const rows=$('guideRows');if(rows.children.length>=20){message('촬영 항목은 최대 20개입니다.',true);return;}
 const row=document.createElement('div');row.className='guide-row';
 const select=document.createElement('select');select.setAttribute('aria-label','촬영 항목 선택');
 for(const text of ['직접 입력',...shotOptions]){const option=document.createElement('option');option.value=text==='직접 입력'?'':text;option.textContent=text;select.append(option);}
 const input=document.createElement('input');input.type='text';input.required=true;input.maxLength=100;input.placeholder='읽어줄 항목 입력';input.value=value;input.setAttribute('aria-label','촬영 안내 내용');
 select.value=shotOptions.includes(value)?value:'';
 select.onchange=()=>{if(select.value)input.value=select.value;guideDirty=true;input.focus();};
 input.oninput=()=>{guideDirty=true;select.value=shotOptions.includes(input.value)?input.value:'';};
 const remove=button('삭제',()=>{row.remove();guideDirty=true;});remove.type='button';remove.setAttribute('aria-label','촬영 항목 삭제');
 row.append(select,input,remove);rows.append(row);
}
$('addGuide').onclick=()=>{addGuideRow();guideDirty=true;$('guideRows').lastElementChild?.querySelector('input').focus();};
$('guideForm').onsubmit=async e=>{e.preventDefault();const steps=[...$('guideRows').querySelectorAll('input')].map(input=>input.value.trim());if(await act({action:'guide',steps},'촬영 안내를 저장했습니다. 입력한 항목만 읽어드립니다.')){guideDirty=false;guide.positions.clear();guide.choose(activeGroup(),0);lastGuideSignature='';renderGuide();warmVoice(steps);}};
function renderGuide(){guide.configure(state.guide_steps||[]);const saved=JSON.stringify(guide.steps);if(!guideDirty&&editorSignature!==saved){editorSignature=saved;$('guideRows').replaceChildren();guide.steps.forEach(addGuideRow);}$('guideSetupStatus').textContent=guide.steps.length?'촬영 안내 '+guide.steps.length+'개 저장됨 · 상품당 4컷 후 자동 전환합니다.':'안내를 입력하지 않으면 촬영 완료만 알려드립니다.';const index=guide.index(activeGroup()),next=guide.next(activeGroup());$('guideCurrent').textContent=next||(guide.steps.length?'추가 촬영 가능':'자유 촬영');$('guidePosition').textContent=next?'안내 '+(index+1)+' / '+guide.steps.length+' · 항목을 누르면 순서를 바꿉니다.':guide.steps.length?'설정한 안내가 끝났습니다. 4컷까지 자유롭게 촬영하세요.':'촬영 준비에서 읽어줄 항목을 입력할 수 있습니다.';['previousGuide','nextGuide'].forEach(id=>$(id).disabled=!guide.steps.length);$('repeatGuide').disabled=!next;const signature=JSON.stringify([guide.steps,index]);if(signature!==lastGuideSignature){lastGuideSignature=signature;$('guideSteps').replaceChildren(...guide.steps.map((text,i)=>{const b=button((i+1)+'. '+text,()=>chooseGuide(i));b.className=i===index?'current':i<index?'past':'';b.setAttribute('aria-current',i===index?'step':'false');return b;}));}}
function captureFeedback(events){if(!events.length)return;for(const event of events){const group=state.groups.find(g=>g.id===event.group);if(group)guide.captured(event,group);}const latest=events[events.length-1],group=state.groups.find(g=>g.id===latest.group),count=group?group.photos.filter(p=>!p.excluded&&!p.deleted_at).length:events.length;const text=events.length>1?events.length+'장 저장 완료':'촬영 완료 · '+count+'장 저장됨';$('captureToast').textContent='✓ '+text;$('captureToast').hidden=false;clearTimeout(successTimer);successTimer=setTimeout(()=>$('captureToast').hidden=true,1800);$('stage').classList.remove('saved-flash');void $('stage').offsetWidth;$('stage').classList.add('saved-flash');clearTimeout(flashTimer);flashTimer=setTimeout(()=>$('stage').classList.remove('saved-flash'),650);$('lastShotStatus').textContent=text;message(text);beep();const complete=latest.product_complete;if(complete){guide.choose(null,0);lastGuideSignature='';$('captureToast').textContent='✓ 4컷 완료 · 다음 상품 준비';message('4컷 완료. 다음 상품을 보여 주세요. 자동으로 새 묶음에 저장합니다.');}const next=complete?guide.next(null):guide.next(group);const spoken=complete?'4컷 촬영 완료. 다음 상품을 놓아 주세요.':events.length>1?events.length+'장 촬영됐습니다.':'촬영됐습니다.';speak(spoken+(next?' 다음 안내. '+next:''),260);}
function imageRect(){const box=$('stage').getBoundingClientRect(),size=state?.resolution||[16,9];return CaptureFlow.fitRect(box.width,box.height,...size);}
function overlay(){if(step!==2)return;const c=$('overlay'),box=$('stage').getBoundingClientRect();c.width=box.width;c.height=box.height;const rect=imageRect(),ctx=c.getContext('2d');ctx.lineWidth=2;ctx.strokeStyle='#8ad4ff';ctx.strokeRect(rect.x+roi[0]*rect.width,rect.y+roi[1]*rect.height,(roi[2]-roi[0])*rect.width,(roi[3]-roi[1])*rect.height);const product=state?.product;if(state?.running&&product?.current&&!selecting){ctx.strokeStyle=product.edge_warning?'#edc46b':'#a5e55b';for(const item of product.objects||[]){const r=product.roi||roi,b=item.box;const x=r[0]+b[0]*(r[2]-r[0]),y=r[1]+b[1]*(r[3]-r[1]);ctx.strokeRect(rect.x+x*rect.width,rect.y+y*rect.height,(b[2]-b[0])*(r[2]-r[0])*rect.width,(b[3]-b[1])*(r[3]-r[1])*rect.height);}}}
function visibleGroups(){return state.groups.filter(g=>g.photos.some(p=>!p.deleted_at));}
function renderBrandSelection(){
 const groups=visibleGroups(),ids=new Set(groups.map(g=>g.id));
 for(const id of selectedGroups)if(!ids.has(id))selectedGroups.delete(id);
 const count=selectedGroups.size;
 $('brandSelectionCount').textContent=count+'개 상품 선택';
 $('selectAllGroups').checked=groups.length>0&&count===groups.length;
 $('selectAllGroups').indeterminate=count>0&&count<groups.length;
 $('selectAllGroups').disabled=busy||!groups.length;
 $('selectUnassigned').disabled=busy||!groups.some(g=>!g.brand.trim());
 $('clearGroupSelection').disabled=busy||!count;
 $('applyBrand').disabled=busy||!count||!$('batchBrand').value.trim();
 $('clearBrands').disabled=busy||!count;
 const selected=groups.filter(g=>selectedGroups.has(g.id)),missing=selected.filter(g=>!g.brand.trim()).length,unreviewed=selected.filter(g=>!g.reviewed).length;
 $('reviewSelected').disabled=busy||!count||missing>0||!unreviewed;
 $('reviewSelected').textContent=count?'선택 '+count+'개 상품 검토 완료':'선택 상품 검토 완료';
 $('batchReviewHint').textContent=!count?'사진을 확인한 상품을 선택해 주세요.':missing?'선택한 상품 중 '+missing+'개는 브랜드 지정이 필요합니다.':!unreviewed?'선택한 상품은 모두 검토 완료했습니다. 폴더 저장으로 이동하세요.':'확인한 '+count+'개 상품을 함께 검토 완료하면 저장할 수 있습니다.';
 const allIds=CaptureFlow.reviewableGroupIds(state.groups),missingAll=groups.filter(g=>!g.brand.trim()).length,noPhotos=groups.filter(g=>g.brand.trim()&&!g.reviewed&&!g.photos.some(p=>!p.excluded&&!p.deleted_at)).length;
 const allLabel='전체 상품 검토 완료'+(allIds.length?' · '+allIds.length+'개':'');
 $('reviewAll').textContent=allLabel;$('reviewAll').disabled=busy||!allIds.length;
 $('reviewAllSave').textContent=allLabel;$('reviewAllSave').disabled=busy||!allIds.length;$('reviewAllSave').hidden=!allIds.length;
 $('allReviewHint').textContent=(allIds.length?'사진을 확인했다면, 상품 선택 없이 현재 작업의 '+allIds.length+'개 상품을 함께 검토 완료합니다.':'검토 가능한 미완료 상품이 없습니다.')+(missingAll?' 브랜드 미지정 '+missingAll+'개는 제외합니다.':'')+(noPhotos?' 저장할 사진이 없는 '+noPhotos+'개는 제외합니다.':'');
 $('brandAssignmentHint').textContent=count?'선택한 '+count+'개 상품 모두에 적용합니다. 기존 브랜드도 변경되며, 변경한 상품은 다시 검토해야 합니다.':'상품 카드의 선택 상자를 먼저 눌러 주세요.';
 const brands=[...new Set(groups.map(g=>g.brand).filter(Boolean))].sort();
 const signature=JSON.stringify(brands);
 if(signature!==brandOptionsSignature){brandOptionsSignature=signature;$('knownBrands').replaceChildren(...brands.map(brand=>{const option=document.createElement('option');option.value=brand;return option;}));}
 document.querySelectorAll('[data-group-select]').forEach(input=>{input.checked=selectedGroups.has(input.dataset.groupSelect);input.disabled=busy;input.closest('.group').classList.toggle('group-selected',input.checked);});
}
$('selectAllGroups').onchange=e=>{selectedGroups.clear();if(e.target.checked)visibleGroups().forEach(g=>selectedGroups.add(g.id));renderBrandSelection();};
$('selectUnassigned').onclick=()=>{selectedGroups.clear();visibleGroups().filter(g=>!g.brand.trim()).forEach(g=>selectedGroups.add(g.id));renderBrandSelection();};
$('clearGroupSelection').onclick=()=>{selectedGroups.clear();renderBrandSelection();};
$('batchBrand').oninput=renderBrandSelection;
async function assignBrand(brand){
 if(busy||!selectedGroups.size)return;
 const ids=[...selectedGroups];
 if(await act({action:'assign_brand',groups:ids,brand},brand?ids.length+'개 상품에 '+brand+' 브랜드를 지정했습니다. 사진을 확인하고 검토 완료해 주세요.':ids.length+'개 상품의 브랜드를 해제했습니다.')){
  selectedGroups.clear();$('batchBrand').value='';renderBrandSelection();
 }
}
$('batchBrandForm').onsubmit=e=>{e.preventDefault();if($('batchBrand').value.trim())assignBrand($('batchBrand').value.trim());};
$('clearBrands').onclick=()=>assignBrand('');
async function reviewProducts(ids){
 if(busy||!ids.length)return false;
 const ok=await act({action:'review_groups',groups:ids},ids.length+'개 상품을 검토 완료했습니다. 이제 폴더 저장에서 저장할 수 있습니다.');
 if(ok)renderBrandSelection();return ok;
}
$('reviewSelected').onclick=()=>{if(!$('reviewSelected').disabled)reviewProducts([...selectedGroups]);};
const reviewAll=async()=>{
 const workId=state.work_id,from=step;
 const ok=await reviewProducts(CaptureFlow.reviewableGroupIds(state.groups));
 if(ok&&state.work_id===workId&&step===from&&step!==4&&!$('reviewNextDialog').open)$('reviewNextDialog').showModal();
};
$('reviewAll').onclick=reviewAll;$('reviewAllSave').onclick=reviewAll;
$('stayAfterReview').onclick=()=>$('reviewNextDialog').close();
$('saveAfterReview').onclick=async()=>{
 $('reviewNextDialog').close();await goStep(4);document.querySelector('[data-panel="4"]').scrollIntoView({block:'start'});
};
$('reviewBeforeSave').onclick=async()=>{
 await goStep(3);selectedGroups.clear();
 visibleGroups().filter(g=>!g.brand.trim()||!g.reviewed).forEach(g=>selectedGroups.add(g.id));
 renderBrandSelection();document.querySelector('[data-panel="3"]').scrollIntoView({block:'start'});
};
function renderGroups(){
 const signature=JSON.stringify([state.groups,state.export_preview]);if(signature===lastSignature)return;lastSignature=signature;
 const container=$('groups');container.replaceChildren();
 if(!visibleGroups().length){const empty=document.createElement('div');empty.className='empty-result';empty.textContent='촬영한 사진이 여기에 쌓입니다. 브랜드는 촬영 후 지정합니다.';container.append(empty);}
 state.groups.forEach((group,index)=>{
  if(!group.photos.some(p=>!p.deleted_at))return;
  const section=document.createElement('article');section.className='group';
  const head=document.createElement('div');head.className='group-head';
  const selectLabel=document.createElement('label');selectLabel.className='check group-select';
  const select=document.createElement('input');select.type='checkbox';select.dataset.groupSelect=group.id;select.setAttribute('aria-label','상품 '+String(index+1).padStart(3,'0')+' 선택');
  select.onchange=()=>{if(select.checked)selectedGroups.add(group.id);else selectedGroups.delete(group.id);renderBrandSelection();};selectLabel.append(select,document.createTextNode('선택'));
  const title=document.createElement('strong');title.textContent='상품 '+String(index+1).padStart(3,'0')+' · '+(group.brand||'브랜드 미지정')+' · '+group.photos.filter(p=>!p.excluded&&!p.deleted_at).length+'컷';
  const badge=document.createElement('span');badge.className='badge'+(group.reviewed&&group.brand?' done':'');badge.textContent=!group.brand?'브랜드 지정 필요':group.reviewed?'검토 완료':'검토 필요';
  const spacer=document.createElement('span');spacer.className='spacer';head.append(selectLabel,title,badge,spacer);
  if(index&&state.groups[index-1].brand===group.brand)head.append(button('앞 묶음과 합치기',()=>act({action:'merge',group:group.id})));
  const review=button(group.reviewed?'검토 다시 열기':'검토 완료',()=>act({action:'review',group:group.id}));review.disabled=!group.reviewed&&!group.brand;head.append(review);
  const path=document.createElement('div');path.className='group-path';path.textContent=group.brand?'저장 폴더: '+((state.export_preview||[]).find(p=>p.id===group.id)?.folder||group.brand+'/상품_'+String(index+1).padStart(3,'0')):'브랜드를 지정하고 검토 완료하면 저장할 수 있습니다.';
  const photos=document.createElement('div');photos.className='photos';
  group.photos.forEach((photo,i)=>{
   if(photo.deleted_at)return;
   const item=document.createElement('div');item.className='photo'+(photo.excluded?' excluded':'');
   const image=document.createElement('img');image.src='/thumbs/'+photo.file;image.alt='상품 '+(index+1)+'의 '+(i+1)+'번째 사진';image.loading='lazy';image.decoding='async';image.tabIndex=0;
   const open=()=>{$('largePhoto').src='/photos/'+photo.file;$('photoDialog').showModal();};image.onclick=open;image.onkeydown=e=>{if(e.key==='Enter')open();};
   const small=document.createElement('small');small.textContent=(i+1)+'컷 · '+(photo.reason==='auto'?'자동':'직접')+' · '+photo.width+'×'+photo.height;
   if(photo.framing_warning){const warning=document.createElement('span');warning.className='photo-warning';warning.textContent='가장자리 닿음 · 잘림 확인';item.append(warning);}
   item.append(image,small,button(photo.excluded?'제외 취소':'내보내기 제외',()=>act({action:'exclude',group:group.id,file:photo.file})),button('사진 삭제',()=>photoAction('delete_photo',group.id,photo.file)));
   if(i)item.append(button('여기부터 나누기',()=>act({action:'split',group:group.id,file:photo.file})));photos.append(item);
  });section.append(head,path,photos);container.append(section);
 });renderTrash();
}
function renderStorage(){
 const selected=state.export_preview||[],approved=selected.length,groups=visibleGroups(),unassigned=groups.filter(g=>!g.brand.trim()).length,pending=groups.filter(g=>g.brand.trim()&&!g.reviewed).length,count=selected.reduce((n,g)=>n+g.count,0);
 $('reviewCount').textContent=unassigned+pending;
 $('reviewSummary').textContent='저장 가능 '+approved+'상품 · 브랜드 미지정 '+unassigned+'상품 · 검토 대기 '+pending+'상품';
 $('localDirectory').textContent=state.export_directory;if(!destinationDirty&&document.activeElement!==$('outputPath'))$('outputPath').value=state.export_directory;
 $('destinationPath').textContent='저장 위치: '+state.export_directory;
 $('exportSummary').textContent=approved+'상품 · '+count+'장 저장 예정 / 브랜드 미지정 '+unassigned+'상품·검토 대기 '+pending+'상품은 제외';
 const tree=['촬영_일시/'];for(const g of selected){tree.push('  '+g.folder+'/');tree.push('    01.jpg ~ '+String(g.count).padStart(2,'0')+'.jpg');}
 if(!approved)tree.push('  사진 확인에서 브랜드 지정과 검토를 완료해 주세요.');$('folderTree').textContent=tree.join('\n');
 $('localSave').disabled=busy||!approved;$('export').disabled=busy||!approved;
 const blocked=!approved&&groups.length>0;
 $('saveBlocker').hidden=!blocked;
 $('saveBlocker').textContent=unassigned?'아직 저장할 수 없습니다. 브랜드 미지정 '+unassigned+'개'+(pending?' · 검토 대기 '+pending+'개':'')+' 상품이 있습니다. 사진 확인에서 브랜드와 사진을 확인하고 검토 완료해 주세요.':pending?'브랜드 지정은 끝났지만 '+pending+'개 상품의 검토가 아직 완료되지 않았습니다. 사진 확인에서 검토 완료를 눌러 주세요.':'현재 상품의 사진이 모두 제외되어 저장할 사진이 없습니다. 사진 확인에서 제외 상태를 확인해 주세요.';
 $('reviewBeforeSave').hidden=!blocked;$('reviewBeforeSave').disabled=busy;
 $('saveHint').textContent=busy?'폴더에 저장 중입니다.':!approved?'사진 확인에서 브랜드 지정과 검토를 완료해 주세요.':'브랜드 지정과 검토를 마친 사진만 복사합니다. 다시 저장하면 새 폴더를 만듭니다.';
 $('savePath').textContent='촬영 원본 보관: '+state.save_directory;
 const saved=state.local_export;$('openFolder').disabled=!saved;$('localResult').hidden=!saved;$('localResult').textContent=saved?'마지막 저장 완료 · '+saved.groups+'묶음 · '+saved.photos+'장\n'+saved.path:'';
 renderBrandSelection();
}
function render(){if(!state)return;renderWork();if(!roiInitialized){roi=state.roi;roiInitialized=true;}$('connect').textContent=state.running?'카메라 멈추기':'카메라 연결';['selectRoi','calibrate','manual'].forEach(id=>$(id).disabled=!state.running||(id==='manual'&&!state.can_capture));$('automatic').classList.toggle('stop',state.automatic);$('automatic').textContent=state.automatic?'자동 촬영 일시정지':'자동 촬영 시작';$('automatic').disabled=!state.automatic&&(!state.running||!state.calibrated||!state.can_capture||state.product?.state!=='ready');$('placeholder').hidden=state.running;$('preview').hidden=!state.running;
if(state.running&&step===2&&!streaming){$('preview').src='/api/stream?start='+Date.now();streaming=true;}if((!state.running||step!==2)&&streaming){$('preview').removeAttribute('src');streaming=false;}
$('resolution').textContent=state.resolution?state.resolution.join(' × ')+' · 전송 '+(state.preview_fps||0)+'fps':'연결 전';$('modelState').textContent=state.product?.state==='ready'?'상품 검출 준비됨':state.product?.state==='loading'?'상품 검출기 준비 중':state.product?.state==='error'?'상품 검출 오류 · 자동 촬영 중지':'상품 검출기 대기';if(state.product?.device)$('modelState').textContent=(state.product.device==='cuda'?'GPU 인식 · ':'CPU 인식 · ')+Math.round(state.product.inference_ms||0)+'ms'+(state.product.device==='cpu'?' · 인식에 시간이 걸릴 수 있습니다':'');const product=state.product||{},feedback=state.capture_status||{title:'촬영 상태 확인 중',detail:''};$('cameraState').textContent=feedback.title;$('captureTitle').textContent=feedback.title;document.querySelector('.capture-feedback').classList.toggle('complete',feedback.code==='next_product');$('captureReason').textContent=feedback.detail;const names=[...new Set((product.objects||[]).map(o=>labels[o.label]||'상품'))].join(' · ');$('recognitionState').textContent=!state.running?'상품 인식 대기':product.current?names+' 인식됨':product.recognized?'이전 상품 인식됨 · 현재 화면 재확인 중':product.state==='ready'?'현재 상품 인식 안 됨':'상품 인식 준비 중';$('recognitionState').className='detection-status'+(state.running&&product.current?' detected':'');$('framingWarning').hidden=!(state.running&&product.current&&product.edge_warning);$('framingWarning').textContent='상품이 촬영 영역 가장자리에 닿았습니다. 잘림 가능성이 있습니다. 가장자리 접촉만으로 자동 촬영을 막지는 않습니다.';
$('headerStatus').textContent=state.running?(state.automatic?'자동 촬영 중':'카메라 연결됨'):'카메라 연결 전';if(state.error)message(state.error,true);
guide.configure(state.guide_steps||[]);const captures=tracker.take(state.events);captureFeedback(captures);const current=activeGroup(),finished=state.waiting_for_product_change&&state.groups.find(g=>g.id===state.last_completed_group),display=current||finished;const count=display?display.photos.filter(p=>!p.deleted_at).length:0;$('activeProduct').textContent=display?'상품 '+String(state.groups.indexOf(display)+1).padStart(3,'0')+(finished?' · 촬영 완료':' · 촬영 중'):'상품 '+String(state.groups.length+1).padStart(3,'0')+' · 준비';$('currentCount').textContent=count;$('shotProgress').replaceChildren(...Array.from({length:4},(_,i)=>{const cell=document.createElement('span');cell.textContent=i<count?'✓':String(i+1).padStart(2,'0');cell.className=i<count?'done':i===count?'next':'';return cell;}));$('progressNote').textContent=finished?'4컷 완료 · 다음 상품을 보여 주세요':'4컷 저장하면 다음 상품으로 자동 전환';$('progressNote').classList.toggle('complete',Boolean(finished));$('captureTiming').textContent=(state.stable_seconds??.65)+'초 정지 확인 후 촬영 · 상품 인식 조건 별도';const sec=Math.floor(state.active_seconds);$('timer').textContent=String(Math.floor(sec/60)).padStart(2,'0')+':'+String(sec%60).padStart(2,'0');const deleted=new Set(state.groups.flatMap(g=>g.photos.filter(p=>p.deleted_at).map(p=>p.file)));const latest=[...state.events].reverse().find(e=>e.event==='capture'&&!deleted.has(e.file));if(!latest){$('lastShot').hidden=true;$('lastShot').removeAttribute('src');delete $('lastShot').dataset.file;$('lastShotStatus').textContent='촬영하면 여기에 표시됩니다';}if(latest){if($('lastShot').dataset.file!==latest.file){$('lastShot').dataset.file=latest.file;$('lastShot').src='/thumbs/'+latest.file;$('lastShot').hidden=false;}if(!captures.length&&$('lastShotStatus').textContent==='촬영하면 여기에 표시됩니다')$('lastShotStatus').textContent='마지막 저장 사진';}renderGuide();renderGroups();renderStorage();overlay();warmVoice(state.guide_steps||[]);}


$('outputPath').oninput=()=>{destinationDirty=true;};
$('destinationForm').onsubmit=async e=>{e.preventDefault();if(await submit('/api/local/destination',{path:$('outputPath').value.trim()},'저장 폴더를 변경했습니다. 다음 결과부터 이 위치에 저장합니다.')){destinationDirty=false;renderStorage();}};
let folderPath=null,folderParent=null,folderLoading=false;
async function loadFolder(path,quiet=false){if(folderLoading)return;folderLoading=true;$('folderPickerError').textContent='폴더를 읽고 있습니다.';$('useFolder').disabled=true;try{const response=await fetch('/api/local/folders'+(path?'?path='+encodeURIComponent(path):''));const result=await response.json();if(!response.ok)throw Error(result.error||'폴더를 읽지 못했습니다.');folderPath=result.path;folderParent=result.parent;$('folderCurrent').textContent=folderPath||'드라이브를 선택하세요';$('folderUp').disabled=!folderParent;$('folderDrives').replaceChildren(...result.drives.map(d=>button(d,()=>loadFolder(d))));$('folderList').replaceChildren(...result.folders.map(f=>button('▸ '+f.name,()=>loadFolder(f.path))));if(!result.folders.length){const empty=document.createElement('p');empty.textContent=folderPath?'이 폴더에는 하위 폴더가 없습니다.':'위에서 드라이브를 선택해 주세요.';$('folderList').append(empty);}$('folderPickerError').textContent=result.truncated?'폴더가 많아 일부만 표시했습니다. 경로 직접 입력도 사용할 수 있습니다.':'';}catch(e){$('folderPickerError').textContent=quiet?'':e.message;}finally{folderLoading=false;$('useFolder').disabled=!folderPath;}}
async function pickDestination(){if(busy)return;folderPath=null;folderParent=null;$('folderDialog').showModal();await loadFolder(null);await loadFolder(state.export_directory,true);}
$('closeFolderDialog').onclick=()=>{$('folderDialog').close();message('폴더 선택을 취소했습니다. 기존 저장 위치를 유지합니다.');};$('folderDialog').addEventListener('cancel',()=>message('폴더 선택을 취소했습니다. 기존 저장 위치를 유지합니다.'));$('folderUp').onclick=()=>loadFolder(folderParent);$('useFolder').onclick=async()=>{if(!folderPath||folderLoading||busy)return;$('useFolder').disabled=true;if(await submit('/api/local/destination',{path:folderPath},'저장 폴더를 변경했습니다. 다음 결과부터 이 위치에 저장합니다.')){destinationDirty=false;renderStorage();$('folderDialog').close();}else{$('folderPickerError').textContent=$('message').textContent;$('useFolder').disabled=false;}};
$('pickDestination').onclick=pickDestination;$('changeDestination').onclick=pickDestination;
$('localSave').onclick=async()=>{
 if(busy)return;
 const b=$('localSave');b.disabled=true;b.textContent='폴더에 저장 중…';$('saveStatus').className='hint';$('saveStatus').textContent='사진을 복사하고 확인하고 있습니다.';
 const ok=await submit('/api/local/save',{},'브랜드·상품별 폴더에 저장했습니다. 저장 폴더 열기로 확인하세요.');
 $('saveStatus').className=ok?'save-success':'error';$('saveStatus').textContent=ok?'저장 완료 · '+state.local_export.photos+'장 · '+state.local_export.path:$('message').textContent;
 b.textContent='폴더로 저장';render();
};
$('openFolder').onclick=()=>submit('/api/local/open',{},'저장 폴더를 열었습니다.');
$('connect').onclick=async()=>{try{audio ||= new AudioContext();await audio.resume();}catch{}if(await submit(state?.running?'/api/stop':'/api/start',{},'카메라 상태를 변경했습니다.')){roi=state.roi;overlay();}};
$('automatic').onclick=async()=>{await unlockAudio();const enabled=!state.automatic;if(await act({action:'automatic',enabled},enabled?'자동 촬영을 시작했습니다.':'자동 촬영을 멈췄습니다.')){if(enabled)speak('자동 촬영을 시작합니다.'+(guideText()?' '+guideText():''));else{voiceToken++;voiceAudio.pause();}}};
$('calibrate').onclick=()=>act({action:'calibrate',roi},'빈 배경 등록 완료. 자동 촬영 시작을 눌러 주세요.');
$('manual').onclick=async()=>{if(busy)return;await unlockAudio();await act({action:'capture'});};$('newGroup').onclick=async()=>{if(await act({action:'new_group'},'다음 사진부터 새 묶음으로 저장합니다.')){guide.choose(null,0);lastGuideSignature='';renderGuide();speak(guideText()||'다음 상품을 촬영하세요.');}};
$('selectRoi').onclick=()=>{selecting=true;$('stage').classList.add('selecting');message('촬영 화면에서 촬영할 공간을 넉넉하게 드래그하세요.');};
function point(e){const box=$('stage').getBoundingClientRect(),rect=imageRect();return [Math.max(0,Math.min(1,(e.clientX-box.left-rect.x)/rect.width)),Math.max(0,Math.min(1,(e.clientY-box.top-rect.y)/rect.height))];}
$('stage').onpointerdown=e=>{if(!selecting)return;drag=point(e);$('stage').setPointerCapture(e.pointerId);};$('stage').onpointermove=e=>{if(!drag)return;const p=point(e);roi=[Math.min(drag[0],p[0]),Math.min(drag[1],p[1]),Math.max(drag[0],p[0]),Math.max(drag[1],p[1])];overlay();};$('stage').onpointerup=()=>{if(!drag)return;drag=null;selecting=false;$('stage').classList.remove('selecting');message('영역을 지정했습니다. 빈 배경을 등록해 주세요.');};
$('closePhoto').onclick=()=>$('photoDialog').close();
async function download(path,name){try{const r=await fetch(path);if(!r.ok){const result=await r.json();throw Error(result.error||'다운로드에 실패했습니다.');}const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(e){message(e.message,true);}}
$('export').onclick=()=>download('/api/export','moacut-reviewed.zip');$('log').onclick=()=>download('/api/state','moacut-camera-log.json');window.addEventListener('resize',overlay);
function renderTrash(){const items=[];state.groups.forEach((group,index)=>group.photos.forEach(photo=>{if(!photo.deleted_at)return;const item=document.createElement('div');item.className='photo';const image=document.createElement('img');image.src='/thumbs/'+photo.file;image.alt='휴지통 사진';image.loading='lazy';const label=document.createElement('small');label.textContent='상품 '+String(index+1).padStart(3,'0')+' · 삭제됨';item.append(image,label,button('사진 복원',()=>photoAction('restore_photo',group.id,photo.file)));items.push(item);}));$('trashCount').textContent='휴지통 · '+items.length+'장';$('trashPhotos').replaceChildren(...items);}
let currentWorkId=null,worksSignature='',promptedDay=null,workChosen=false;
function selectedWorkInfo(){const work=(state.works||[]).find(w=>w.work_id===$('workSelect').value);$('workSelectedInfo').textContent=work?work.work_date+' · '+work.groups+'묶음 · '+work.photos+'장'+(work.legacy_work?' · 날짜별로 나누기 전 기존 자료':''):'';$('continueWork').textContent=work?.work_date===state.today?'선택 작업 이어하기':'선택 작업 사진 확인';}
function openWork(){if($('workDialog').open)return;voiceToken++;voiceAudio.pause();if(state.automatic)act({action:'automatic',enabled:false});$('workError').textContent='';$('workName').value=state.today+' 촬영';$('closeWork').hidden=!workChosen;$('workDialog').showModal();selectedWorkInfo();}
function renderWork(){
 if(currentWorkId!==state.work_id){currentWorkId=state.work_id;tracker=new CaptureFlow.CaptureTracker();guide=new CaptureFlow.GuideProgress();lastSignature='';lastGuideSignature='';guideDirty=false;editorSignature=null;voiceToken++;voiceAudio.pause();$('captureToast').hidden=true;$('lastShotStatus').textContent='촬영하면 여기에 표시됩니다';selectedGroups.clear();$('batchBrand').value='';brandOptionsSignature='';$('saveStatus').textContent='';if($('reviewNextDialog').open)$('reviewNextDialog').close();}
 $('workTitle').textContent=state.work_name;$('workInfo').textContent=state.work_date+' · '+state.groups.reduce((n,g)=>n+g.photos.filter(p=>!p.deleted_at).length,0)+'장'+(!state.can_capture?' · 지난 작업 · 사진 확인/저장만 가능':'');
 const signature=JSON.stringify(state.works);if(signature!==worksSignature){const previous=$('workSelect').value;worksSignature=signature;$('workSelect').replaceChildren(...state.works.map(work=>{const option=document.createElement('option');option.value=work.work_id;option.textContent=work.work_date+' · '+work.work_name+' · '+work.photos+'장';return option;}));$('workSelect').value=state.works.some(w=>w.work_id===previous)?previous:state.work_id;selectedWorkInfo();}
 $('continueWork').disabled=busy;$('newWork').disabled=busy;
 if(promptedDay!==state.today){promptedDay=state.today;openWork();}
}
async function chooseWork(payload){if(busy)return;const ok=await submit('/api/work',payload);if(ok){workChosen=true;$('workDialog').close();await goStep(state.can_capture?1:3);message(state.can_capture?'선택한 작업에서 진행합니다.':'지난 작업을 열었습니다. 사진 확인과 저장이 가능합니다.');}else $('workError').textContent=$('message').textContent;}
$('chooseWork').onclick=openWork;$('workSelect').onchange=selectedWorkInfo;$('continueWork').onclick=()=>chooseWork({mode:'continue',work_id:$('workSelect').value});$('newWorkForm').onsubmit=e=>{e.preventDefault();chooseWork({mode:'new',name:$('workName').value.trim()});};$('closeWork').onclick=()=>$('workDialog').close();$('workDialog').addEventListener('cancel',e=>{if(!workChosen)e.preventDefault();});
async function poll(){if(polling||busy)return;polling=true;try{const r=await fetch('/api/state');if(!r.ok)throw Error('연결 오류');state=await r.json();render();}catch{message('촬영 도구와 연결이 끊겼습니다. 실행 상태를 확인해 주세요.',true);}finally{polling=false;}}
document.addEventListener('keydown',e=>{if(step!==2||e.repeat||busy||($('photoDialog').open||$('folderDialog').open||$('workDialog').open||$('reviewNextDialog').open)||e.target.closest('input,textarea,select,button,[contenteditable]'))return;if(e.code==='Space'&&!$('manual').disabled){e.preventDefault();$('manual').click();}else if(e.code==='KeyN'){e.preventDefault();$('newGroup').click();}});
poll();setInterval(poll,250);
