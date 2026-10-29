const test=require('node:test'),assert=require('node:assert/strict');
const {CaptureTracker,GuideProgress,fitRect}=require('./web/capture-flow.js');
test('only newly saved captures notify; replay and other events do not',()=>{
  const tracker=new CaptureTracker(),old={event:'capture',file:'old'};
  assert.deepEqual(tracker.take([old]),[]);
  const first={event:'capture',file:'one'},second={event:'capture',file:'two'};
  assert.deepEqual(tracker.take([old,{event:'camera_error'},first,second]),[first,second]);
  assert.deepEqual(tracker.take([old,first,second]),[]);
});
test('custom guidance can skip/repeat without claiming photo types or forcing an end',()=>{
  const guide=new GuideProgress();guide.configure(['사용자가 정한 앞면','사용자 라벨']);
  guide.choose(null,1);
  const group={id:'g',photos:[{file:'first'}]};guide.captured({file:'first'},group);
  assert.equal(guide.next(group),'');
  group.photos.push({file:'extra'});guide.captured({file:'extra'},group);
  assert.equal(guide.index(group),3);
  guide.choose(group,0);assert.equal(guide.next(group),'사용자가 정한 앞면');
  assert.deepEqual(guide.steps,['사용자가 정한 앞면','사용자 라벨']);
  guide.configure(['새 안내']);assert.equal(guide.next(null),'새 안내');
});
test('image coordinates retain aspect ratio in a shorter preview',()=>{
  assert.deepEqual(fitRect(800,300,1920,1080),{x:133.33333333333331,y:0,width:533.3333333333334,height:300});
  assert.deepEqual(fitRect(400,400,400,800),{x:100,y:0,width:200,height:400});
});
test('fourth shot resets guidance for the next product without a click',()=>{
  const guide=new GuideProgress();guide.configure(['앞','뒤','라벨','옆']);
  const first={id:'one',photos:['a','b','c','d'].map(file=>({file}))};
  for(const [i,photo] of first.photos.entries())guide.captured({file:photo.file,product_complete:i===3},first);
  assert.equal(guide.next(null),'앞');
  const second={id:'two',photos:[{file:'e'}]};guide.captured({file:'e'},second);
  assert.equal(guide.next(second),'뒤');
});

test('resumed guidance ignores photos in trash',()=>{
  const guide=new GuideProgress();guide.configure(['앞','뒤','라벨','상세']);
  const group={id:'g',photos:[{file:'deleted',deleted_at:'today'},{file:'kept'}]};
  assert.equal(guide.index(group),1);
  assert.equal(guide.next(group),'뒤');
});
