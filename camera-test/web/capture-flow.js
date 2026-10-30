(function(root){
  class CaptureTracker {
    constructor(){this.ready=false;this.seen=new Set();}
    take(events){
      const captures=events.filter(e=>e.event==='capture');
      const fresh=this.ready?captures.filter(e=>!this.seen.has(e.file)):[];
      captures.forEach(e=>this.seen.add(e.file));this.ready=true;
      return fresh;
    }
  }
  class GuideProgress {
    constructor(){this.steps=[];this.positions=new Map();}
    configure(steps){if(JSON.stringify(steps)!==JSON.stringify(this.steps)){this.steps=[...steps];this.positions.clear();}}
    index(group){return this.positions.get(group?.id||'next')??(group?.photos.filter(p=>!p.deleted_at).length||0);}
    choose(group,index){this.positions.set(group?.id||'next',Math.max(0,Math.min(this.steps.length,index)));}
    captured(event,group){
      let index=this.positions.get(group.id);
      if(index===undefined)index=this.positions.get('next')??Math.max(0,group.photos.findIndex(p=>p.file===event.file));
      this.positions.delete('next');this.positions.set(group.id,index+1);
      if(event.product_complete)this.positions.set('next',0);
    }
    next(group){return this.steps[this.index(group)]||'';}
  }
  function fitRect(width,height,imageWidth=16,imageHeight=9){
    const scale=Math.min(width/imageWidth,height/imageHeight);
    const w=imageWidth*scale,h=imageHeight*scale;
    return {x:(width-w)/2,y:(height-h)/2,width:w,height:h};
  }
  function reviewableGroupIds(groups){
    return groups.filter(g=>g.brand.trim()&&!g.reviewed&&g.photos.some(p=>!p.excluded&&!p.deleted_at)).map(g=>g.id);
  }
  const api={CaptureTracker,GuideProgress,fitRect,reviewableGroupIds};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.CaptureFlow=api;
})(typeof window==='undefined'?{}:window);
