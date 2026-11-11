import { AuthScreen } from './AuthScreen.jsx';
import { previewUrl, shotTimeLabels, resultContent, narrationPatch, workbenchLocation, taskCharges, hasActiveTasks, listPagePath, exportError, assetsForExport, formatYuan, workStatusLabel, productUploadError, creationQuoteError } from './work-contract.mjs';
import { request, setCsrfToken, idempotencyKey } from './api';
const DEMO = new URLSearchParams(location.search).get('demo') === '1';
const {useState,useEffect,useRef}=React;
const pages=['工作台','商品档案','一键出片','创作方案','素材与分镜','我的作品','任务中心'];
const iconPaths=['M4 10 12 3l8 7M6 9v11h12V9','M5 7 12 3l7 4v10l-7 4-7-4zM5 7l7 4 7-4M12 11v10','M4 7h16M7 4v6M4 17h16M16 14v6','M5 5h14v14H5M9 9h6M9 13h4','M5 4h14v16H5zM5 16l5-5 4 4 3-3 2 2','M8 5 19 12 8 19z','M6 5h12M6 12h12M6 19h8'];
const seed={products:[{name:'轻音无线耳机',spec:'雾白 · 单规格',code:'1001',confirmed:true,type:0,files:['商品正面图','产品说明书'],version:2},{name:'轻风高速吹风机',spec:'暖砂 · 单规格',code:'1002',confirmed:false,type:1,files:['商品正面图','参数说明'],version:1},{name:'随行无线耳机',spec:'岩灰 · 单规格',code:'1003',confirmed:true,type:0,files:['商品正面图'],version:1}],current:0,settings:{platforms:[true,false],duration:'15',audience:'城市通勤人群',goal:'商品卖点展示',method:'原图合成与场景生成',budget:30,brief:'突出轻巧便携与通勤场景，保留商品真实外观。'},scripts:[['通勤路上，给自己留一点空间。','轻巧入袋，随取随听。','让音乐陪你，轻装出发。'],['出门前，装好今天的小小快乐。','圆润机身，放进口袋刚刚好。','选一首喜欢的歌，开始今天的旅程。']],plan:1,history:[],repairSpent:0,authorized:false,generated:false,assets:[{name:'白底图',state:'待复核',version:1},{name:'通勤场景',state:'待复核',version:1},{name:'桌面场景',state:'待复核',version:1}],checks:[false,false,false],canceled:false,failed:true,videoVersion:1,title:['通勤路上，轻装出发','口袋里的通勤搭子'],subtitle:'白字 · 底部居中',exports:[true,true,false,true]};
const solidIcons=["<rect x=\"3\" y=\"3\" width=\"8\" height=\"8\" rx=\"2.5\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"2.5\"/><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"2.5\"/><circle cx=\"17\" cy=\"17\" r=\"4\"/>", "<path d=\"M8 3h8l2 4H6zM5 8h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2\"/><path d=\"M9 12h6\" stroke=\"white\" stroke-width=\"2\"/>", "<rect x=\"3\" y=\"5\" width=\"18\" height=\"3\" rx=\"1.5\"/><circle cx=\"15\" cy=\"6.5\" r=\"4\"/><rect x=\"3\" y=\"16\" width=\"18\" height=\"3\" rx=\"1.5\"/><circle cx=\"8\" cy=\"17.5\" r=\"4\"/>", "<path d=\"m4 16-1 6 6-1L19 11l-5-5zM16 4l2-2a2 2 0 0 1 3 3l-2 2z\"/>", "<rect x=\"3\" y=\"4\" width=\"18\" height=\"17\" rx=\"4\"/><circle cx=\"16\" cy=\"9\" r=\"2\" fill=\"white\"/><path d=\"m5 18 5-6 4 4 3-2 3 4\" fill=\"white\"/>", "<rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"5\"/><path d=\"m10 8 6 4-6 4z\" fill=\"white\"/>", "<rect x=\"3\" y=\"3\" width=\"18\" height=\"19\" rx=\"4\"/><path d=\"M8 8h8M8 12h8M8 16h5\" stroke=\"white\" stroke-width=\"2\"/>"];
function NavIcon({n}){return <svg className="navicon solid-icon" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{__html:solidIcons[n]}}/>}
function I({n=0}){return <svg className="navicon" viewBox="0 0 24 24" aria-hidden="true"><path d={iconPaths[n]} /></svg>}
function Tag({children,warn=false}){return <span className={'tag '+(warn?'warn':'')}>{children}</span>}
function Art({type=0,scene=0,small=false}){return <div className={'art scene'+scene+(small?' small':'')} role="img" aria-label={type?'吹风机设计示意':'耳机设计示意'}><div className="orb"></div><div className={type?'dryer':'product'}><span></span></div><div className="plinth"></div></div>}
function Field({label,children}){return <label className="field">{label}{children}</label>}

const flowNavShapes=[
 '<path d="M10.2 3a3 3 0 0 1 3.6 0l7 5.5a1.5 1.5 0 0 1-.9 2.7H19V19a2 2 0 0 1-2 2h-3v-6h-4v6H7a2 2 0 0 1-2-2v-7.8h-.9a1.5 1.5 0 0 1-.9-2.7z"/>',
 '<path d="m12 2 9 4.5-9 4.5L3 6.5zM3 9l8 4v9l-7-3.5a2 2 0 0 1-1-1.8zm10 4 8-4v8.7a2 2 0 0 1-1 1.8L13 22z"/>',
 '<rect x="3" y="2" width="12" height="15" rx="3"/><rect x="7" y="9" width="15" height="12" rx="3" stroke="white" stroke-width="1.5"/><path d="m13 12 5 3-5 3z" fill="white"/>',
 '<path d="M3 6a3 3 0 0 1 3-3h4l3 3h5a3 3 0 0 1 3 3v1H3zM2 12h20l-1.6 7a3 3 0 0 1-3 2H6.6a3 3 0 0 1-3-2z"/>',
 '<rect x="3" y="3" width="18" height="19" rx="4"/><path d="m7 9 1.5 1.5L11 8m-4 8 1.5 1.5L11 15M14 9h3m-3 7h3" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
];
function FlowNavIcon({n}){return <svg className="navicon solid-icon" viewBox="0 0 24 24" aria-hidden="true" dangerouslySetInnerHTML={{__html:flowNavShapes[n]}}/>}

const FLOW_KEY='marketing-flow-v4';
const FLOW_NAMES=['创作首页','商品资料','视频与海报','作品管理','生成任务'];
const FLOW_STAGES=['创作文案','编排画面','配音与字幕','视频与海报'];
const TASK_ACTION_LABELS={pause:'暂停制作',resume:'继续制作',cancel:'取消后续步骤',recover:'恢复失败阶段',manual_copy:'手工接管',query:'核查视频状态',static_fallback:'选择静图替代'};
function taskStatus(task){
 return ({queued:'待开始',running:task.pause_requested?'暂停中':'生成中',paused:'已暂停',unknown:'结果待核查（已停止推进）',external_unknown:'结果待核查（已停止推进）',recovery_required:'结果待核查（已停止推进）',failed:'生成失败',partial:'部分完成',canceled:'已取消',succeeded:'已完成'})[task.execution_state]||task.execution_state;
}
const clone=v=>JSON.parse(JSON.stringify(v));
function demoContent(p,style='自然介绍'){
 return {posterTitle:[p.name+'，日常新灵感',p.name+'的日常搭配'],posterLine:['从真实细节出发，选择适合自己的好物','把日常好物，放进喜欢的生活'],posterScene:[0,2],title:[p.name+'，日常新灵感',p.name+'的日常分享'],body:['从外观与细节认识'+p.name+'，选购前请核对商品规格。','今天分享'+p.name+'，从真实外观开始，找到适合自己的选择。'],scripts:[['看看这件日常好物。','从细节了解'+p.name+'。','选购前，核对适合自己的规格。'],['今天的日常分享，从这里开始。','一起看看'+p.name+'的外观。','根据自己的需要，选择合适的商品。']],images:[0,1,2],voice:'自然女声',music:'轻快日常',subtitle:'白字深底',style};
}
function initialFlow(){if(!DEMO)return {products:[],runs:[],current:null,prefs:{platforms:[true,false],duration:'15',budget:30,brief:''}};try{const saved=JSON.parse(localStorage.getItem(FLOW_KEY));if(saved){saved.runs=saved.runs.map(r=>{const d=demoContent(r.product);return {...r,content:r.content?{...d,...r.content}:r.content,draft:r.draft?{...d,...r.draft}:r.draft}});return saved;}const old=JSON.parse(localStorage.getItem('marketing-prototype-v3'));const products=old?.products||seed.products;const pref=old?.settings||seed.settings;const migrated=[];if(old?.generated){const content={...demoContent(products[old.current||0]),title:old.title,scripts:old.scripts,body:old.copyBody||['',''],subtitle:old.subtitle?.startsWith('黑')?'黑字浅底':'白字深底'};migrated.push({id:'legacy-'+Date.now(),product:clone(products[old.current||0]),platforms:pref.platforms,duration:+pref.duration,status:'待复核',stage:4,content:clone(content),draft:clone(content),revision:1,reviewed:[],history:[],spent:0,budget:pref.budget,created:Date.now(),legacy:true})}return {products,prefs:{platforms:pref.platforms,duration:pref.duration,budget:pref.budget,brief:''},runs:migrated,current:null}}catch{return {products:clone(seed.products),prefs:{platforms:[true,false],duration:'15',budget:30,brief:''},runs:[],current:null}}}
const realContent=resultContent;
const mapWork=(w,products)=>({...w,product:products.find(p=>p.id===w.sku_id)||{name:'商品',spec:'',files:[],type:0},platforms:['douyin','xiaohongshu'].map(p=>w.platforms?.includes(p)),duration:w.duration_seconds,status:w.status,stage:0,spent:w.settled_amount||0,created:w.created_at,revision:w.revision,restoreTarget:w.draft?.restore_revision_id,content:w.result?realContent(w.result.copy,{},w.result.render_settings):null,draft:w.result?realContent(w.result.copy,w.draft,w.result.render_settings):null,media_url:previewUrl(w.assets,'video',w.platforms?.[0]),asset_ids:w.assets?.map(a=>a.id)||[],history:[]});
function FlowApp(){
 const [db,setDb]=useState(initialFlow),[page,setPage]=useState(()=>workbenchLocation(location.hash).page),[selected,setSelected]=useState(()=>Math.max(0,db.products.findIndex(p=>p.code===db.prefs.productCode))),[platform,setPlatform]=useState(0),[editor,setEditor]=useState(''),[mediaMode,setMediaMode]=useState('视频'),[modal,setModal]=useState(null),[error,setError]=useState(''),[toast,setToast]=useState(''),[query,setQuery]=useState(''),[filter,setFilter]=useState('全部'),[playing,setPlaying]=useState(false),[time,setTime]=useState(0),[scenario,setScenario]=useState('正常生成');
 const dialog=useRef(null),focusBefore=useRef(null);
 const reloadRevision=useRef(0);
 const [paging,setPaging]=useState(false);
 const [musicRights,setMusicRights]=useState(false),[uploadingMusic,setUploadingMusic]=useState(false);
 const savingProduct=useRef(false);
 const taskCursor=db.taskCursors?.at(-1);
 const [needsLogin,setNeedsLogin]=useState(false),[checkingSession,setCheckingSession]=useState(!DEMO),[sessionError,setSessionError]=useState(false);
 async function reloadData(){
 const revision=++reloadRevision.current;
 const [products,works,tasks]=await Promise.all([request('/skus'),request(listPagePath('works',db.workCursors?.at(-1))),request(listPagePath('tasks',taskCursor))]);
 const mapped=await Promise.all(products.items.map(async p=>{const profiles=await request('/skus/'+p.id+'/profiles');const sources=await request('/skus/'+p.id+'/sources');const selection=await request('/skus/'+p.id+'/source-selection');const profile=profiles.items.find(x=>x.id===profiles.current_profile_id&&x.status==='confirmed');return {...p,code:p.model,spec:p.color,sources:sources.items,sourceSelection:selection.selection,files:sources.items.map(x=>x.name||x.filename),source_ids:sources.items.filter(x=>x.type!=='audio').map(x=>x.id),confirmed:!!profile,profile_id:profile?.id,type:0,version:p.revision}}));
 const workId=workbenchLocation(location.hash).workId;
 const details=await Promise.all(works.items.map(w=>request('/works/'+w.id)));
 if(workId&&!details.some(w=>w.id===workId)){
  try{details.push(await request('/works/'+encodeURIComponent(workId)))}catch(e){if(e.status!==404)throw e;setToast('当前作品不可用')}
 }
 if(reloadRevision.current===revision)setDb(v=>({...v,products:mapped,runs:details.map(w=>mapWork(w,mapped)),workListIds:works.items.map(w=>w.id),workNext:works.next_cursor,tasks:tasks.items,taskNext:tasks.next_cursor}));
 }
 async function changeListPage(collection,forward){
  if(paging)return;
  const cursors=collection==='works'?(db.workCursors||[]):(db.taskCursors||[]);
  const next=collection==='works'?db.workNext:db.taskNext;
  if(forward?!next:!cursors.length)return;
  const trail=forward?[...cursors,next]:cursors.slice(0,-1);
  const revision=++reloadRevision.current;
  setPaging(true);
  try{
   const result=await request(listPagePath(collection,trail.at(-1)));
   const works=collection==='works'?await Promise.all(result.items.map(w=>request('/works/'+encodeURIComponent(w.id)))):null;
   if(revision!==reloadRevision.current)return;
   setDb(v=>{
    if(!works)return {...v,tasks:result.items,taskNext:result.next_cursor,taskCursors:trail};
    const runs=works.map(w=>mapWork(w,v.products));
    const current=v.runs.find(w=>w.id===v.current);
    if(current&&!runs.some(w=>w.id===current.id))runs.push(current);
    return {...v,runs,workListIds:result.items.map(w=>w.id),workNext:result.next_cursor,workCursors:trail};
   });
  }catch(e){setToast(e.message)}finally{setPaging(false)}
 }
 useEffect(()=>{if(DEMO)return;request('/sessions/current').then(session=>{setCsrfToken(session.csrf_token);return reloadData()}).catch(e=>{if(e.status===401)setNeedsLogin(true);else setSessionError(true)}).finally(()=>setCheckingSession(false))},[]);
 
 const run=db.runs.find(x=>x.id===db.current),product=db.products[selected]||db.products[0]||{name:'请先新建商品',spec:'',files:[],type:0};
 const pollingWorkId=page===2?db.current:null;
 const activityRevision=reloadRevision.current;
 const pollActive=!DEMO&&!paging&&page===4&&hasActiveTasks(db.tasks||[]);
 useEffect(()=>{
  if(!pollActive)return;
  const controller=new AbortController();
  let timer;
  async function poll(){
   try{
    if(document.visibilityState!=='visible')return;
    const revision=reloadRevision.current;
    const options={signal:controller.signal};
    const tasks=await request(listPagePath('tasks',taskCursor),options);
    if(!controller.signal.aborted&&revision===reloadRevision.current){
     setDb(v=>({...v,tasks:tasks.items,taskNext:tasks.next_cursor}));
    }
   }catch(e){if(!controller.signal.aborted&&e.status===401){controller.abort();setNeedsLogin(true)}}
   finally{if(!controller.signal.aborted)timer=setTimeout(poll,3000)}
  }
  timer=setTimeout(poll,3000);
  return()=>{controller.abort();clearTimeout(timer)};
 },[pollActive,taskCursor]);
 useEffect(()=>{
  if(DEMO||!pollingWorkId||needsLogin)return;
  const controller=new AbortController();
  let timer;
  async function pollWork(){
   let again=true;
   try{
    if(document.visibilityState!=='visible')return;
    const revision=reloadRevision.current;
    const work=await request('/works/'+encodeURIComponent(pollingWorkId)+'?include_activity=true',{signal:controller.signal});
    if(controller.signal.aborted||revision!==reloadRevision.current)return;
    setDb(v=>{
     const previous=v.runs.find(w=>w.id===work.id);
     if(previous?.revision>work.revision)return v;
     const updated=mapWork(work,v.products);
     return {...v,runs:previous?v.runs.map(w=>w.id===work.id?updated:w):[...v.runs,updated]};
    });
    again=work.has_active_tasks;
   }catch(e){
    if(e.status===401||e.status===404){again=false;if(e.status===401&&!controller.signal.aborted)setNeedsLogin(true)}
   }finally{if(again&&!controller.signal.aborted)timer=setTimeout(pollWork,3000)}
  }
  pollWork();
  return()=>{controller.abort();clearTimeout(timer)};
 },[pollingWorkId,needsLogin,activityRevision]);
 const textDirty=!DEMO&&!!run?.content&&['title','body'].some(key=>JSON.stringify(run.draft[key])!==JSON.stringify(run.content[key]));
 const dirty=!!run?.restoreTarget||textDirty||!!run&&JSON.stringify({...run.draft,title:[],body:[]})!==JSON.stringify({...run.content,title:[],body:[]});
 const posterDirty=!!run&&['posterTitle','posterLine','posterScene'].some(k=>JSON.stringify(run.draft?.[k])!==JSON.stringify(run.content?.[k]));
 const shotPictureDirty=!DEMO&&!!run?.content&&run.draft.shots.some((shots,p)=>shots.some((shot,i)=>{
  const current=run.content.shots[p][i];
  return shot.repair_asset_id||shot.asset_slot!==current?.asset_slot||shot.visual_description!==current?.visual_description||
   shot.video_source_id!==current?.video_source_id||shot.start_seconds!==current?.start_seconds;
 }));
 const videoDirty=shotPictureDirty||!!run?.content&&['scripts','images','voice','music','subtitle'].some(k=>JSON.stringify(run.draft[k])!==JSON.stringify(run.content[k]));
 const active=['生成中','已暂停','待处理','待核查','更新中'];
 useEffect(()=>{if(!DEMO)return;try{localStorage.setItem(FLOW_KEY,JSON.stringify(db))}catch{setToast('本机保存失败，请勿关闭页面')}},[db]);
 useEffect(()=>{if(modal){focusBefore.current=document.activeElement;dialog.current.showModal()}else if(dialog.current?.open){dialog.current.close();focusBefore.current?.focus()}},[!!modal]);
 useEffect(()=>{const f=()=>{if(location.hash==='#content')return;const route=workbenchLocation(location.hash);setPage(route.page);if(!DEMO&&route.page===2)setDb(v=>({...v,current:route.workId}))};f();addEventListener('hashchange',f);return()=>removeEventListener('hashchange',f)},[]);
 useEffect(()=>{if(toast){const t=setTimeout(()=>setToast(''),2800);return()=>clearTimeout(t)}},[toast]);
 useEffect(()=>{if(!playing||!run)return;const t=setInterval(()=>setTime(v=>{if(v>=run.duration){setPlaying(false);return 0}return v+1}),1000);return()=>clearInterval(t)},[playing,run?.id]);
 useEffect(()=>{setPlaying(false);setTime(0);setEditor('');setMusicRights(false);if(run)setPlatform(run.platforms[0]?0:1)},[run?.id,page]);
 useEffect(()=>{if(!DEMO)return;const waiting=db.runs.filter(r=>r.status==='生成中'||r.status==='更新中');if(!waiting.length)return;const t=setTimeout(()=>setDb(v=>({...v,runs:v.runs.map(r=>{if(r.status==='更新中')return {...r,status:'待复核',content:clone(r.draft),revision:r.revision+1,reviewed:[],spent:r.spent+2};if(r.status!=='生成中')return r;if(r.stage===1&&r.scenario==='文案失败'&&!r.recovered)return {...r,status:'待处理',problem:'文案创作失败',recovered:true};if(r.stage===2&&r.scenario==='结果未知'&&!r.recovered)return {...r,status:'待核查',unknownReservation:8,problem:'画面生成结果未知',recovered:true};if(r.stage<3)return {...r,stage:r.stage+1};const content=r.manualContent||demoContent(r.product);return {...r,status:'待复核',stage:4,content:clone(content),draft:clone(content),spent:8}})})),900);return()=>clearTimeout(t)},[db.runs]);
 function patchRun(p,id=run?.id){if(!DEMO){setToast('请通过服务端保存草稿或执行任务操作');return;}setDb(v=>({...v,runs:v.runs.map(r=>r.id===id?{...r,...p}:r)}))}
 function nav(p,workId=db.current){setPage(p);location.hash=!DEMO&&p===2&&workId?'2?'+new URLSearchParams({work:workId}):p;setError('');window.scrollTo(0,0)}
 async function open(type,data={}){setError('');const opened={type,...data,...(!DEMO&&type==='update'&&run?{workId:run.id,revision:run.revision,runKey:idempotencyKey()}: {})};if(!DEMO&&type==='product'){const selected=db.products[data.index]?.sourceSelection?.sources;opened.previewSources={product:selected?.product?.source_id||'',mask:selected?.mask?.source_id||''};}setModal(opened);if(!DEMO&&type==='product'){try{const documentFacts=await request('/skus/'+encodeURIComponent(db.products[data.index].id)+'/fact-candidates');setModal(v=>v?.type==='product'&&v.index===opened.index?{...v,documentFacts}:v)}catch(e){setError(e.message)}return;}if(!DEMO&&run&&['versions','rewrite','update','facts'].includes(type)){try{const response=await request('/works/'+run.id+(type==='facts'?'/fact-sources?platform='+['douyin','xiaohongshu'][platform]:type==='versions'?'/history':type==='rewrite'?'/copy-candidates':'/change-quotes'),type==='update'?{method:'POST'}:{});setModal(v=>v===opened?{...v,remote:response}:v)}catch(e){setError(e.message)}}}
 function close(){setModal(null);setError('')}
 function pref(k,v){setDb(d=>({...d,prefs:{...d.prefs,[k]:v}}))}
 function start(i=selected){if(!db.products[i]){open('new');return;}setSelected(i);setDb(v=>({...v,current:null,prefs:{...v.prefs,productCode:v.products[i].code}}));nav(2,null)}
 function view(r){setDb(v=>({...v,current:r.id}));nav(2,r.id);if(!DEMO&&!db.runs.some(w=>w.id===r.id))reloadData().catch(e=>setToast(e.message))}
 function edit(p){if(!DEMO){saveRealDraft(p);return;}patchRun({draft:{...run.draft,...p},reviewed:[],status:'待复核'})}
 function saveText(k,value){const arr=[...run.draft[k]];arr[platform]=value;edit({[k]:arr})}
 function err(msg){setError(msg);return false}
 async function preflight(){
  if(!product?.confirmed)return err('请先核对商品事实并确认档案。');
  if(!db.prefs.platforms.some(Boolean))return err('至少选择一个发布平台。');
  if(!Number.isInteger(+db.prefs.duration)||+db.prefs.duration<=0)return err('视频时长请输入正整数秒数。');
  if(!Number.isFinite(+db.prefs.budget)||+db.prefs.budget<=0)return err('请在高级设置中填写大于0的预算上限。');
  if(DEMO){
   if(!Number.isFinite(+db.prefs.budget)||+db.prefs.budget<8)return err('预算不足，请在高级设置中将预算调整至本次演示上界8元或以上。');
   open('generate');return;
  }
  if(!product.profile_id)return err('请先确认商品档案。');
  const input={profile_id:product.profile_id,platforms:['douyin','xiaohongshu'].filter((_,i)=>db.prefs.platforms[i]),duration_seconds:+db.prefs.duration,brief:db.prefs.brief,budget_limit:String(db.prefs.budget)};
  const opened={type:'generate',input,productName:product.name,runKey:idempotencyKey()};
  setError('');setModal(opened);
  try{
   const creationRequest=await request('/creation-requests',{method:'POST',body:JSON.stringify(input)});
   setModal(v=>v===opened?{...v,creationRequest}:v);
  }catch(e){setModal(v=>v===opened?{...v,quoteError:creationQuoteError(e)}:v)}
 }
 function downloadPoster(){if(!DEMO){exportReal('poster_only');return;}const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([posterSvg(run,platform)],{type:'image/svg+xml;charset=utf-8'}));a.download=run.product.name+'-'+['抖音','小红书'][platform]+'-海报示意图.svg';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);setToast('海报示意图已下载，非真实发布素材')}
 function download(review=false,mode='完整套件'){if(!DEMO){exportReal(mode==='仅视频'?'video_only':mode==='仅海报'?'poster_only':'full_suite',review);return;}const lines=['营销工作台 · 视频与海报演示清单',review?'已完成原型复核，非真实发布素材':'内部样片 · 未审核','导出范围：'+mode,'商品：'+run.product.name,'成片第'+run.revision+'版','时长：'+run.duration+'秒'];run.platforms.forEach((on,i)=>{if(on){lines.push(['抖音','小红书'][i],run.draft.title[i],run.draft.body[i]);if(mode!=='仅视频')lines.push('海报标题：'+run.content.posterTitle[i],'海报卖点：'+run.content.posterLine[i]);if(mode!=='仅海报')lines.push(...run.content.scripts[i])}});lines.push('仅本机交互演示，不包含真实模型生成媒体。');const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([lines.join('\n')],{type:'text/plain;charset=utf-8'}));a.download='营销作品演示清单.txt';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);setToast('演示清单已下载')}
 async function saveRealDraft(p){
 const fields={scripts:'narration',subtitle:'subtitle_style',posterTitle:'poster_title',posterLine:'poster_points',posterScene:'poster_layout',images:'asset_id'};
 let changes={platform:['douyin','xiaohongshu'][platform],...Object.fromEntries(Object.entries(p).map(([k,v])=>[fields[k]||k,Array.isArray(v)&&['title','body','posterTitle','posterLine','posterScene','scripts'].includes(k)?v[platform]:v]))};
 if(typeof changes.poster_points==='string')changes.poster_points=changes.poster_points.trim()?[changes.poster_points.trim()]:[];
 if(p.scripts)changes=narrationPatch(run.draft.scripts[platform],p.scripts[platform],['douyin','xiaohongshu'][platform]);
 try{const saved=await request('/works/'+run.id+'/draft',{method:'PATCH',body:JSON.stringify({expected_revision:run.revision,changes})});setDb(v=>({...v,runs:v.runs.map(r=>{
  if(r.id!==run.id)return r;
  const draft={...r.draft,...p};
  for(const key of ['voice','music','subtitle'])if(key in p)draft[key]=r.draft[key].map((value,i)=>i===platform?p[key]:value);
  return {...r,revision:saved.revision,draft};
 })}))}catch(e){setToast(e.message)}
 }
 async function discardDraft(){
  if(DEMO){patchRun({draft:{...clone(run.content),title:clone(run.draft.title),body:clone(run.draft.body)}});setEditor('');return;}
  try{
   await request('/works/'+encodeURIComponent(run.id)+'/draft',{method:'PATCH',body:JSON.stringify({expected_revision:run.revision,changes:{},discard:true})});
   await reloadData();setEditor('');
  }catch(e){setToast(e.message)}
 }
 async function uploadMusic(event){
  const input=event.currentTarget,file=input.files[0];
  if(!file||!musicRights||uploadingMusic)return;
  setUploadingMusic(true);
  try{
   await request('/skus/'+encodeURIComponent(run.sku_id)+'/sources',{method:'POST',body:file,
    headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Rights-Confirmed':'true'}});
   await reloadData();setMusicRights(false);
  }catch(e){setToast(e.detail?.message||e.message)}finally{setUploadingMusic(false);input.value=''}
 }
 async function parseProductDocument(source,skuId){
  setError('');setModal(v=>v?.type==='product'?{...v,parsing:source.id}:v);
  try{
   const parsed=await request('/sources/'+encodeURIComponent(source.id)+'/parse',{method:'POST'});
   if(parsed.parse_status!=='failed')await request('/sources/'+encodeURIComponent(source.id)+'/fact-candidates',{method:'POST'});
  }catch(e){err(e.detail?.message||e.message)}
  finally{
   try{
    const facts=await request('/skus/'+encodeURIComponent(skuId)+'/fact-candidates');
    await reloadData();
    setModal(v=>v?.type==='product'&&v.parsing===source.id?{...v,parsing:null,documentFacts:facts}:v);
   }catch(e){err(e.message);setModal(v=>v?.type==='product'?{...v,parsing:null}:v)}
  }
 }
 async function uploadSupplement(event){
  const input=event.currentTarget,file=input.files[0];
  if(!file||!modal.uploadRights||modal.uploadingSupplement)return;
  const problem=productUploadError(file);
  if(problem){input.value='';return err(problem)}
  const skuId=db.products[modal.index].id;
  setError('');setModal(v=>({...v,uploadingSupplement:true}));
  try{
   await request('/skus/'+encodeURIComponent(skuId)+'/sources',{method:'POST',body:file,headers:{
    'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Rights-Confirmed':'true',
   }});
   await reloadData();setToast('素材已上传');
  }catch(e){err(e.detail?.message||e.message)}
  finally{input.value='';setModal(v=>v?.type==='product'?{...v,uploadingSupplement:false,uploadRights:false}:v)}
 }
 function selectPreviewSource(role,id){
  setModal(v=>({...v,previewSources:{...v.previewSources,[role]:id},previewSizes:{...v.previewSizes,[role]:null},subjectPreview:null}));
 }
 function subjectPreviewUrl(productModal){
  const {product,mask}=productModal.previewSources;
  if(!product||!mask||product===mask||!productModal.previewSizes?.product||productModal.previewSizes.product!==productModal.previewSizes.mask)return null;
  const skuId=db.products[productModal.index].id;
  return '/api/v1/skus/'+encodeURIComponent(skuId)+'/subject-preview?'+new URLSearchParams({product_id:product,mask_id:mask});
 }
 function recordPreviewSize(role,id,event){
  const {naturalWidth,naturalHeight}=event.currentTarget;
  setModal(v=>v?.type==='product'&&v.previewSources?.[role]===id?
   {...v,previewSizes:{...v.previewSizes,[role]:`${naturalWidth}×${naturalHeight}`}}:v);
 }
 async function taskAction(task,action){try{const detail=await request('/tasks/'+task.id);if(!detail.next_actions?.includes(action))throw new Error('任务当前不允许此操作');if(action==='static_fallback'){setModal({type:'staticFallback',task:detail});return;}if(action==='manual_copy'){setModal({type:'manual',task:detail});return;}await request('/tasks/'+task.id+'/actions',{method:'POST',body:JSON.stringify({action})});await reloadData()}catch(e){setToast(e.message)}}
 async function reviewAsset(id,decision){try{await request('/assets/'+id+'/reviews',{method:'POST',body:JSON.stringify({decision,reason:decision==='reject'?'用户标记画面问题':''})});await reloadData();setToast(decision==='adopt'?'已采用当前资产版本':'已拒用当前资产版本')}catch(e){setToast(e.message)}}
 async function applyRepair(assetId){
  try{
   await request('/assets/'+encodeURIComponent(assetId)+'/apply-repair',{method:'POST',body:JSON.stringify({expected_revision:run.revision})});
   await reloadData();
   setToast('修复图已应用到当前作品');
  }catch(e){setToast(e.detail?.code==='PENDING_DRAFT'?'请先应用或撤销未应用修改':e.message)}
 }
 async function saveShotPicture(index,change){
  try{
   await request('/works/'+run.id+'/draft',{method:'PATCH',body:JSON.stringify({expected_revision:run.revision,changes:{platform:['douyin','xiaohongshu'][platform],shots:[{index,...change}]}})});
   await reloadData();
  }catch(e){setToast(({
   VIDEO_SOURCE_REQUIRED:'请选择当前商品已确认使用权的 MP4。',
   VIDEO_SOURCE_TRIM_INVALID:'从指定起点开始的视频长度不足，请调整截取起点。',
   VIDEO_SOURCE_HASH_MISMATCH:'视频文件校验失败，请重新上传。',
  })[e.detail?.code]||e.message)}
 }
 function videoSourceAction(shot,index){
  const videos=(run.product.sources||[]).filter(source=>source.type==='video'&&source.rights_confirmed);
  if(!videos.length)return null;
  return <form key={platform+':'+index+':'+(shot.video_source_id||'')+':'+(shot.start_seconds??0)}
   onSubmit={event=>{
    event.preventDefault();
    const data=new FormData(event.currentTarget);
    saveShotPicture(index,{video_source_id:data.get('video_source_id'),start_seconds:Number(data.get('start_seconds'))});
   }}>
   <Field label="商品视频"><select name="video_source_id" required defaultValue={shot.video_source_id||''}>
    <option value="" disabled>选择已上传的 MP4</option>
    {videos.map(source=><option key={source.id} value={source.id}>{source.name}</option>)}
   </select></Field>
   <Field label="截取起点（秒）"><input name="start_seconds" type="number" min="0" max="119.99" step="0.01" required defaultValue={shot.start_seconds??0}/></Field>
   <button type="submit">引用此视频片段</button>
  </form>;
 }
 function repairShotAction(shot,index){
  const asset=run.assets?.find(item=>item.slot===shot.asset_slot&&item.media_kind==='product_image'&&item.repair_render_available&&item.review==='approved');
  return asset&&<button disabled={shot.repair_asset_id===asset.id} onClick={()=>saveShotPicture(index,{repair_asset_id:asset.id})}>
   {shot.repair_asset_id===asset.id?'已选用修复图':'用修复图重制'}
  </button>;
 }
 async function exportReal(selection,release=false,assetIds){try{const pack=await request('/export-packages',{method:'POST',body:JSON.stringify({work_id:run.id,mode:release?'release':'sample',selection,asset_ids:assetIds})});const link=document.createElement('a');link.href='/api/v1/exports/'+encodeURIComponent(pack.id)+'/download';link.download='';link.click();return true}catch(e){if(modal?.type==='review')err(exportError(e.detail));else setToast(exportError(e.detail));return false}}
 async function submit(e){e.preventDefault();const f=new FormData(e.currentTarget);
  if(!DEMO){try{
   if(modal.type==='staticFallback'){
    const shots=f.getAll('shots');if(!shots.length||!f.get('consent'))return err('请选择失败镜头并确认静图替代。');
    await request('/tasks/'+modal.task.id+'/actions',{method:'POST',body:JSON.stringify({action:'static_fallback',authorized:true,shots})});await reloadData();close();return;
   }
   if(modal.type==='update'){
    const shown=modal.remote;
    if(!shown)return err('等待服务端报价后再确认。');
    if(modal.workId!==run.id||modal.revision!==run.revision)return err('草稿已更新，请重新打开报价并确认。');
    if(shown.blockers?.length)return err(shown.blockers.join('；'));
    if(!shown.executable)return err('当前修改不可执行。');
    if(shown.requires_authorization&&!f.get('consent'))return err('请确认修改影响与费用。');
    if(shown.requires_authorization&&!shown.quote_id)return err('报价凭证缺失，请重新打开报价并确认。');
    await request('/works/'+modal.workId+'/apply',{method:'POST',headers:{'Idempotency-Key':modal.runKey},body:JSON.stringify({expected_revision:modal.revision,authorized:!!f.get('consent'),quote_id:shown.quote_id})});
    await reloadData();close();return;
   }
   if(modal.type==='rewrite'){
    if(modal.candidateId){await request('/copy-versions/'+modal.candidateId+'/adopt',{method:'POST',body:JSON.stringify({expected_revision:run.revision})});await reloadData();close();return;}
    if(!f.get('consent'))return err('请确认本次改写授权。');
    const key=modal.runKey||idempotencyKey();setModal(v=>({...v,runKey:key}));await request('/works/'+run.id+'/rewrite',{method:'POST',headers:{'Idempotency-Key':key},body:JSON.stringify({expected_revision:run.revision,platform:['douyin','xiaohongshu'][platform],instruction:f.get('tone')+'：'+f.get('scope'),authorized:true})});setToast('改写任务已提交，完成后可在候选中采用');close();return;
   }
   if(modal.type==='review'){
    if(!f.get('rights'))return err('请确认素材使用权、规格和标识。');
    const selection=modal.exportMode==='仅视频'?'video_only':modal.exportMode==='仅海报'?'poster_only':'full_suite';
    if(run.missing_items?.length){
     const selected=f.getAll('exportAsset');
     if(!selected.length)return err('请选择已复核的交付文件。');
     if(await exportReal(selection,f.get('partialMode')==='release',selected))close();return;
    }
    if(run.platforms.some((on,i)=>on&&!f.get('platform'+i)))return err('请核对所有所选平台的交付内容。');
    const assets=assetsForExport(run.assets||[],selection);if(!assets.length)return err('暂无可复核的真实资产。');
    if(assets.some(asset=>asset.review==='rejected'))return err('所选文件含已拒用版本，请先在作品中处理。');
    try{
     for(const asset of assets.filter(asset=>asset.review!=='approved'))await request('/assets/'+encodeURIComponent(asset.id)+'/reviews',{method:'POST',body:JSON.stringify({decision:'adopt',expected_review:'pending'})});
    }catch(e){await reloadData();return err(exportError(e.detail))}
    if(await exportReal(selection,true))close();
    await reloadData();return;
   }
   if(modal.type==='new'){
    if(savingProduct.current)return;
    if(!f.get('name')?.trim()||!f.get('code')?.trim()||!f.get('spec')?.trim())return err('请填写商品名称、编号及规格。');
    if(modal.fileObjects?.length&&!f.get('rights'))return err('请确认素材使用权。');
    savingProduct.current=true;
    setModal(v=>({...v,saving:true}));
    try{
     const p=modal.createdSku||await request('/skus',{method:'POST',body:JSON.stringify({name:f.get('name'),model:f.get('code'),color:f.get('spec'),merchant_sku:f.get('code'),specification:f.get('spec')})});
     setModal(v=>v?.type==='new'?{...v,createdSku:p}:v);
     const results=new Map(modal.uploadResults||[]);
     for(const file of modal.fileObjects||[]){
      if(['uploaded','unknown'].includes(results.get(file)?.status))continue;
      const inputError=productUploadError(file);
      if(inputError)results.set(file,{status:'failed',message:inputError});
      else try{
       await request('/skus/'+p.id+'/sources',{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream','X-Filename':encodeURIComponent(file.name),'X-Rights-Confirmed':'true'}});
       results.set(file,{status:'uploaded'});
      }catch(e){
       const unknown=!e.status||e.status>=500;
       results.set(file,{status:unknown?'unknown':'failed',message:unknown?'请先在商品档案核对该文件是否已入库。':e.detail?.message||e.message});
      }
      setModal(v=>v?.type==='new'?{...v,uploadResults:new Map(results)}:v);
     }
     await reloadData();
     if([...results.values()].some(value=>value.status!=='uploaded'))return err('商品已保存。失败文件可重新选择后上传。');
     close();nav(1);return;
    }finally{savingProduct.current=false;setModal(v=>v?.type==='new'?{...v,saving:false}:v)}
   }
   if(modal.type==='product'){
    if(!f.get('facts'))return err('请核对商品事实与来源。');
    const p=db.products[modal.index];
    const productSource=f.get('product_source'),maskSource=f.get('mask_source');
    if(!productSource||!maskSource||!f.get('source_reviewed'))return err('请选择商品原图与同尺寸遮罩，并确认主体范围。');
    const candidateIds=Array.from(f.entries()).filter(([key])=>key==='candidate'||key.startsWith('candidate:')).map(([,value])=>value);
    if(modal.documentFacts?.conflicting_keys.some(key=>!modal.documentFacts.items.some(item=>item.key===key&&candidateIds.includes(item.id))))return err('请先为每项冲突事实选择一个来源。');
    await request('/skus/'+p.id+'/source-selection',{method:'POST',body:JSON.stringify({expected_revision:p.revision,product_source_id:productSource,mask_source_id:maskSource,reviewed:true})});
    const profile=await request('/skus/'+p.id+'/profiles',{method:'POST',body:JSON.stringify({facts:{name:p.name,model:p.code,color:p.spec},source_ids:p.source_ids||[],candidate_ids:candidateIds})});
    await request('/profiles/'+profile.id+'/confirm',{method:'POST'});
    await reloadData();close();return;
   }
   if(modal.type==='generate'){
    const cr=modal.creationRequest;
    if(!cr?.quote||cr.status!=='ready')return err('本次生成尚无可授权的报价。');
    if(!f.get('consent'))return err('请确认资料处理范围和费用上界。');
    try{
     const task=await request('/creation-requests/'+encodeURIComponent(cr.id)+'/runs',{method:'POST',headers:{'Idempotency-Key':modal.runKey},body:JSON.stringify({authorized:true})});
     nav(2,task.work_id);await reloadData();close();return;
    }catch(e){
     if(['CREATION_QUOTE_CHANGED','AUTHORIZATION_SCOPE_CHANGED','BUDGET_HELD_FOR_REVIEW'].includes(e.detail?.code)){
      setModal(v=>v?.runKey===modal.runKey?{...v,creationRequest:null,quoteError:'预算或授权条件已变化，请关闭弹窗后重新报价。'}:v);
      return;
     }
     throw e;
    }
   }
   if(modal.type==='cancel'){
    await taskAction(modal.task,'cancel');close();return;
   }
   if(modal.type==='repair'){
    const original=f.get('repair_original'),mask=f.get('repair_mask');
    if(!original||!mask||original===mask)return err('请选择不同的原图与修复遮罩。');
    await request('/assets/'+encodeURIComponent(modal.assetId)+'/repairs',{method:'POST',
      headers:{'Idempotency-Key':modal.runKey},body:JSON.stringify({original_source_id:original,mask_source_id:mask})});
    await reloadData();close();setToast('修复任务已提交');return;
   }
   if(modal.type==='manual'){
    if(!f.get('consent'))return err('请确认使用人工稿继续原任务。');
    const draft={};
    for(const [i,p] of ['douyin','xiaohongshu'].entries()){
     if(!modal.task.manual_copy_platforms.includes(p))continue;
     const title=f.get('title'+i)?.trim(),body=f.get('body'+i)?.trim(),poster_title=f.get('posterTitle'+i)?.trim();
     const points=f.get('posterPoints'+i)?.trim(),shots=[0,1,2].map(j=>f.get('shot'+j+i)?.trim());
     if(!title||!body||!poster_title||!points||shots.some(s=>!s))return err('请补齐所选平台的文案、海报和口播。');
     draft[p]={title,body,poster_title,selling_points:[points],shots};
    }
    await request('/tasks/'+encodeURIComponent(modal.task.id)+'/actions',{method:'POST',body:JSON.stringify({action:'manual_copy',manual_copy:draft,authorized:true})});
    await reloadData();close();return;
   }
   return err('此操作尚未获得服务端可执行状态。');
  }catch(e){return err(e.detail?.code==='REPAIR_SOURCE_REVIEW_REQUIRED'?exportError(e.detail):e.message)}}

  if(modal.type==='generate'){if(!f.get('consent'))return err('请确认资料处理范围与费用上界。');const r={id:'work-'+Date.now(),product:clone(product),platforms:clone(db.prefs.platforms),duration:+db.prefs.duration,brief:db.prefs.brief,budget:+db.prefs.budget,status:'生成中',stage:0,revision:1,reviewed:[],history:[],spent:0,created:Date.now(),scenario};setDb(v=>({...v,current:r.id,runs:[r,...v.runs]}));close();}
  else if(modal.type==='manual'){const c=demoContent(run.product);for(let i=0;i<2;i++){if(!run.platforms[i])continue;const values=['title','body','shot0','shot1','shot2'].map(k=>(f.get(k+i)||'').trim());if(values.some(v=>!v))return err('请补齐所选平台标题、发布文案和三镜口播。');c.title[i]=values[0];c.body[i]=values[1];c.scripts[i]=values.slice(2)}patchRun({manualContent:c,status:'生成中',stage:1,origin:'人工创作'});close()}
  else if(modal.type==='update'){if(!f.get('consent'))return err('请确认本次修改影响及费用。');if(run.spent+2>run.budget)return err('剩余预算不足，请先调整预算上限。');if(run.draft.scripts.some((a,i)=>run.platforms[i]&&a.some(t=>!t.trim())))return err('口播不能为空，请补齐或使用智能改写。');patchRun({status:'更新中',history:[{revision:run.revision,content:clone(run.content),draft:clone(run.draft)},...run.history],reviewed:[]});close();setEditor('')}
  else if(modal.type==='review'){const exportMode=modal.exportMode||'完整套件';if(exportMode==='仅海报'?posterDirty:exportMode==='仅视频'?videoDirty:dirty)return err('修改尚未应用，请先更新样片。');if(exportMode!=='仅海报'&&run.badShots?.length)return err('存在已标记的问题画面，请替换后更新样片。');if(run.platforms.some((on,i)=>on&&(!run.draft.title[i].trim()||!run.draft.body[i].trim())))return err('标题和发布文案不能为空。');if(!run.platforms.every((on,i)=>!on||f.get('platform'+i)))return err('请逐个平台确认当前画面与营销文案。');if(!f.get('rights'))return err('请确认素材使用权、规格和标识。');patchRun({status:exportMode==='完整套件'?'已复核':'部分已复核',reviewed:run.platforms.map((on,i)=>on?i:null).filter(x=>x!==null),content:{...run.content,title:clone(run.draft.title),body:clone(run.draft.body)}});download(true,exportMode);close()}
  else if(modal.type==='rewrite'){if(modal.phase!=='candidate'){const scope=f.get('scope'),tone=f.get('tone');const base=scope==='发布文案'?run.draft.body[platform]:run.draft.scripts[platform][0];setModal({...modal,phase:'candidate',scope,tone,original:base,candidate:tone==='更简洁'?run.product.name+'，从真实细节开始了解。':'一起看看'+run.product.name+'，为日常选择增加一点灵感。'});return}patchRun({copyHistory:[{draft:clone(run.draft),revision:run.revision},...(run.copyHistory||[])]});const k=modal.scope==='发布文案'?'body':'scripts';if(k==='body'){saveText('body',modal.candidate)}else{const scripts=clone(run.draft.scripts);scripts[platform][0]=modal.candidate;edit({scripts})}setToast('已采用候选，原版本保留');close()}
  else if(modal.type==='product'){if(!f.get('facts'))return err('请核对商品事实与来源。');const p=db.products[modal.index];if(!p.files.some(n=>/正面图|\.(png|jpe?g)$/i.test(n)))return err('请补充商品图片后确认。');setDb(v=>({...v,products:v.products.map((x,i)=>i===modal.index?{...x,confirmed:true}:x)}));setSelected(modal.index);close();start(modal.index)}
  else if(modal.type==='new'){if(!f.get('name')?.trim()||!f.get('code')?.trim()||!f.get('spec')?.trim())return err('请填写商品名称、编号及规格。');if(db.products.some(p=>p.code===f.get('code')))return err('商品编号已存在。');if(!modal.files?.length)return err('请添加商品图片。');if(!f.get('rights'))return err('请确认素材使用权。');setDb(v=>({...v,products:[...v.products,{name:f.get('name'),code:f.get('code'),spec:f.get('spec'),files:modal.files,type:f.get('type')==='吹风机'?1:0,confirmed:false,version:1}]}));close();nav(1)}
  else if(modal.type==='cancel'){patchRun({status:'已取消'});close();setToast('已停止后续步骤，已有记录保留')}
  else if(modal.type==='budget'){const value=+f.get('budget');if(!Number.isFinite(value)||value<run.spent)return err('预算不能低于已发生演示费用。');patchRun({budget:value});close()}
  else close();
 }
 const card=(p,i)=><article className="card" key={p.code}><Art type={p.type} scene={i%3}/><div className="cardbody"><div className="row"><h2>{p.name}</h2><Tag warn={!p.confirmed}>{p.confirmed?'已确认':'待确认'}</Tag></div><div className="specrow">{p.spec}<span>{p.files.length} 份资料</span></div><div className="cardfooter"><button onClick={()=>open('product',{index:i})}>查看档案</button><button className={p.confirmed?'primary':''} onClick={()=>p.confirmed?start(i):open('product',{index:i})}>{p.confirmed?'用此商品创作':'确认商品事实'}</button></div></div></article>;
 const workCard=r=><article className="card" key={r.id}><Art type={r.product.type}/><div className="cardbody"><div className="row"><h2>{r.product.name}</h2><Tag warn={r.status!=='已复核'}>{DEMO?r.status:workStatusLabel(r.status)}</Tag></div><div className="specrow">{r.platforms.map((on,i)=>on?['抖音','小红书'][i]:'').filter(Boolean).join('、')}<span>{r.duration} 秒 · 第 {r.revision} 版</span></div><div className="cardfooter"><span>{r.created?new Date(r.created).toLocaleDateString('zh-CN'):'创建时间未知'}</span><button onClick={()=>view(r)}>{r.content?'打开作品':'查看进度'}</button></div></div></article>;
 const home=<><div className="launchgrid"><section className="hero"><h2>选好商品<br/>视频海报一起创作</h2><button className="dark" onClick={()=>start()}>开始一键生成</button><div className="hero-art"><Art/></div></section><section className="panel journey"><h2>三步完成营销创作</h2>{[['选择商品','商品事实一次确认，后续创作直接复用'],['一键生成','文案、视频与配套海报自动完成'],['复核导出','满意即可导出，需要时再修改']].map(([n,t],i)=><div className="journey-row" key={n}><span>{i+1}</span><b>{n}</b><div>{t}</div></div>)}</section></div><section className="section"><div className="bar"><h2>最近作品</h2><button onClick={()=>nav(3)}>全部作品</button></div>{db.runs.length?<div className="grid">{db.runs.slice(0,3).map(workCard)}</div>:<div className="panel empty"><h2>从第一件商品开始</h2><button onClick={()=>start()}>一键生成</button></div>}</section><section className="section"><div className="bar"><h2>可用商品</h2><button onClick={()=>nav(1)}>管理商品</button></div><div className="grid">{db.products.slice(0,3).map(card)}</div></section></>;
 const catalog=<><div className="bar"><div className="tabs">{['全部','已确认','待确认'].map(x=><button key={x} className={filter===x?'selected':''} onClick={()=>setFilter(x)}>{x}</button>)}</div><input aria-label="搜索商品名称" placeholder="搜索商品名称" value={query} onChange={e=>setQuery(e.target.value)}/></div><div className="grid">{db.products.map((p,i)=>({p,i})).filter(({p})=>p.name.includes(query)&&(filter==='全部'||p.confirmed===(filter==='已确认'))).map(({p,i})=>card(p,i))}</div>{!db.products.some(p=>p.name.includes(query))&&<div className="empty">没有匹配商品<button onClick={()=>setQuery('')}>清空搜索</button></div>}</>;
 function posterView(content,i,small=false){return <div className={'marketing-poster poster-platform-'+i+(small?' poster-small':'')}><div className="poster-top"><span>日常好物</span><span>{run.product.name}</span></div><h2>{content.posterTitle?.[i]||run.product.name}</h2><p>{content.posterLine?.[i]||'从商品细节开始了解'}</p><Art type={run.product.type} scene={content.posterScene?.[i]||0}/><div className="poster-bottom"><b>发现日常新灵感</b><span>{run.product.spec}</span></div><span className="poster-demo">海报设计示意</span></div>}
 const steps=<div className="flow-steps" aria-label="创作流程">{['选择商品','一键生成','复核导出'].map((n,i)=><div key={n} className={i===(!run?0:run.content?2:1)?'current':''}><span>{i+1}</span>{n}</div>)}</div>;
 const setup=<><div className="quick-create"><section className="panel"><div className="bar"><h2>选择商品</h2><button onClick={()=>open('choose')}>更换商品</button></div><div className="one-product"><Art type={product.type}/><div><h2>{product.name}</h2><div className="lineitem">{product.spec}<Tag warn={!product.confirmed}>{product.confirmed?'事实已确认':'待确认'}</Tag></div><button onClick={()=>open('product',{index:selected})}>查看事实来源</button></div></div><div className="two"><div className="field">发布平台<div className="platform-picker">{['抖音','小红书'].map((n,i)=><label className="choice" key={n}><input type="checkbox" checked={db.prefs.platforms[i]} onChange={e=>pref('platforms',db.prefs.platforms.map((v,j)=>i===j?e.target.checked:v))}/>{n}</label>)}</div></div><Field label="视频时长（秒）"><input type="number" min="1" step="1" value={db.prefs.duration} onChange={e=>pref('duration',e.target.value)}/></Field></div><details><summary>高级设置</summary><Field label="创意要求（选填）"><textarea value={db.prefs.brief} onChange={e=>pref('brief',e.target.value)} placeholder="留空即可根据商品资料自动创作"/></Field><Field label="预算上限（元）"><input type="number" value={db.prefs.budget} onChange={e=>pref('budget',e.target.value)}/></Field><div className="lineitem">受众、语气、配音与配乐<Tag>自动匹配</Tag></div></details>{error&&<div role="alert" className="error">{error}</div>}<div className="bottom"><Tag>营销文案自动创作</Tag><button className="primary" onClick={preflight}>一键生成</button></div></section><section className="panel"><h2>本次作品</h2>{[['营销视频',db.prefs.platforms.filter(Boolean).length+' 条'],['营销海报',db.prefs.platforms.filter(Boolean).length+' 张'],['标题与发布文案','按平台生成'],['商品图与视频封面','自动配套'],['配音、字幕、配乐','自动匹配']].map(([n,v])=><div className="lineitem" key={n}>{n}<b>{v}</b></div>)}<div className="automation-mark"><NavIcon n={5}/><b>视频与海报，一次生成</b></div></section></div><details hidden={!DEMO} className="scenario"><summary>演示场景</summary><Field label="生成场景"><select value={scenario} onChange={e=>setScenario(e.target.value)}>{['正常生成','文案失败','结果未知'].map(n=><option key={n}>{n}</option>)}</select></Field><span>仅演示状态切换，不调用外部服务。</span></details></>;
 const creationTask=run?.creation_task;
 const resultVersion=DEMO?run?.revision:run?.result?.result_number;
 const resultVersionLabel=resultVersion?`第 ${resultVersion} 版`:'当前结果';
 const creationStatus=creationTask?taskStatus(creationTask):'正在读取任务';
 const progress=!DEMO?run&&<section className="panel generation">
  <div className="bar"><h2>{({'生成中':'正在制作作品','待开始':'等待制作','已暂停':'制作已暂停','已取消':'制作已取消','暂停中':'正在暂停制作'})[creationStatus]||creationStatus}</h2><Tag>{run.product.name}</Tag></div>
  <div className="generation-steps">{FLOW_STAGES.map((name,index)=><div className={creationTask?.progress_stage===index?'current':''} key={name}>
   <span>{index<creationTask?.progress_stage?'已完成':creationTask?.progress_stage===index?creationStatus:'待执行'}</span><b>{name}</b>
  </div>)}</div>
  {creationTask?.error&&<div className="notice" role="alert"><b>{creationTask.error.stage}：{creationTask.error.message}</b><p>{creationTask.error.hint}</p></div>}
  {creationTask?.unknown_cost_flag&&<div className="notice">{taskCharges(creationTask).join(' · ')}</div>}
  <div className="bottom"><button onClick={()=>nav(4)}>查看任务</button>
   {creationTask?.next_actions.map(action=><button key={action} onClick={()=>action==='cancel'?open('cancel',{task:creationTask}):taskAction(creationTask,action)}>{TASK_ACTION_LABELS[action]}</button>)}
   {creationStatus==='已取消'&&<button onClick={()=>start()}>新建创作</button>}
  </div>
 </section>:run&&<section className="panel generation"><div className="bar"><h2>{run.status==='生成中'?'正在制作作品':run.status==='更新中'?'正在应用修改':run.status==='已暂停'?'制作已暂停':run.status==='已取消'?'制作已取消':'需要处理'}</h2><Tag>{run.product.name}</Tag></div><div className="generation-steps">{FLOW_STAGES.map((n,i)=><div className={run.stage===i?'current':''} key={n}><span>{run.status==='更新中'?(i===3?'重新合成':'按修改范围复用'):i<run.stage?'已完成':run.stage===i?run.status:'待执行'}</span><b>{n}</b></div>)}</div>{['待处理','待核查'].includes(run.status)&&<div className="notice"><b>{run.problem}</b><p>{run.status==='待核查'?'保留当前请求和费用预留，核查前不会重新提交。':'已完成内容保留，仅恢复失败阶段。'}</p></div>}<div className="bottom"><button onClick={()=>nav(4)}>查看任务</button>{run.status==='生成中'&&<button onClick={()=>patchRun({status:'已暂停'})}>暂停制作</button>}{run.status==='已暂停'&&<button className="primary" onClick={()=>patchRun({status:'生成中'})}>继续制作</button>}{run.status==='待处理'&&<><button className="primary" onClick={()=>patchRun({status:'生成中'})}>恢复失败阶段</button><button onClick={()=>open('manual')}>手工接管</button></>}{run.status==='待核查'&&<button onClick={()=>open('unknown')}>核查状态</button>}{['生成中','已暂停','待处理','待核查'].includes(run.status)&&<button onClick={()=>open('cancel')}>取消后续步骤</button>}{run.status==='已取消'&&<button onClick={()=>start()}>新建创作</button>}</div></section>;
 const shotTiming=shotTimeLabels(run?.draft?.shots?.[platform]||[]);
 const currentShot=run?.content?Math.min(2,Math.floor(time/(run.duration/3))):0;
 const result=run?.content&&<><div className="output-tabs">{['视频','海报'].map(n=><button key={n} className={mediaMode===n?'selected':''} onClick={()=>{setMediaMode(n);setEditor('');setPlaying(false)}}>{n}</button>)}</div><div className="bar"><div className="tabs">{run.platforms.map((on,i)=>on&&<button key={i} className={platform===i?'selected':''} onClick={()=>{setPlatform(i);setTime(0)}}>{['抖音','小红书'][i]}</button>)}</div><div className="tabs"><Tag warn={run.status!=='已复核'}>{DEMO?run.status:workStatusLabel(run.status)} · {resultVersionLabel}</Tag><button onClick={()=>open('versions')}>历史版本</button><button onClick={()=>start()}>新建创作</button></div></div><div className="result-grid"><section className="panel">{!DEMO?<div className="player">{previewUrl(run.assets,mediaMode==='视频'?'video':'marketing_poster',['douyin','xiaohongshu'][platform])?(mediaMode==='视频'?<video key={previewUrl(run.assets,'video',['douyin','xiaohongshu'][platform])} className="result-media" controls preload="metadata" aria-label="当前平台视频" src={previewUrl(run.assets,'video',['douyin','xiaohongshu'][platform])}/>:<img className="result-media" alt="营销海报" src={previewUrl(run.assets,'marketing_poster',['douyin','xiaohongshu'][platform])}/>):<div className="empty">暂无可预览媒体</div>}</div>:mediaMode==='视频'?<><div className={'player '+(playing?'playing':'')}><div className="film"><span className="sample-label">交互样片 · 第 {run.revision} 版</span><Art type={run.product.type} scene={run.content.images[currentShot]}/><div className={'caption '+(run.content.subtitle==='黑字浅底'?'light':'')}>{run.content.scripts[platform][currentShot]}</div></div></div><div className="playbar"><button onClick={()=>setPlaying(!playing)}>{playing?'暂停':'播放'}</button><input aria-label="播放进度" type="range" min="0" max={run.duration} value={time} onChange={e=>setTime(+e.target.value)}/><span>{time} / {run.duration} 秒</span></div></>:<div className="poster-stage">{posterView(run.content,platform)}</div>}<div className="edit-actions">{(mediaMode==='海报'?[['poster','修改海报']]:[['copy','改文案'],['image','换画面'],['sound','换声音']]).map(([id,n])=><button key={id} className={editor===id?'selected':''} aria-expanded={editor===id} onClick={()=>setEditor(editor===id?'':id)}>{n}</button>)}</div></section><section className="panel result-copy"><div className="bar"><h2>{mediaMode==='海报'?'海报与发布文案':'营销文案'}</h2><Tag>{run.origin||(DEMO?'智能创作演示':'智能创作')}</Tag></div><Field label="发布标题"><input value={run.draft.title[platform]} onChange={e=>saveText('title',e.target.value)}/></Field><Field label="发布文案"><textarea value={run.draft.body[platform]} onChange={e=>saveText('body',e.target.value)}/></Field><button onClick={()=>open('rewrite',{phase:'request'})}>智能改写</button><div className="lineitem">商品事实来源<button onClick={()=>open('facts')}>查看</button></div>{dirty?<div className="notice"><b>有修改尚未应用</b><p>预览保留{resultVersionLabel}，更新后再复核。</p><button className="primary" onClick={()=>open('update')}>更新样片</button><button onClick={discardDraft}>撤销未应用修改</button></div>:<button className="primary full" onClick={()=>open('review')}>复核并导出</button>}{mediaMode==='海报'&&<button className="full" onClick={downloadPoster}>{DEMO?'下载海报示意图':'下载海报样片包'}</button>}<button className="full" onClick={()=>download()}>{DEMO?'下载视频与海报清单':'下载视频与海报样片包'}</button></section></div>
 {editor&&<section className="panel section edit-panel"><div className="bar"><h2>{editor==='poster'?'海报编辑':editor==='copy'?'文案与分镜':editor==='image'?'画面调整':'声音与字幕'}</h2><button onClick={()=>setEditor('')}>收起编辑</button></div>{editor==='poster'?<div className="three"><Field label="海报标题"><input maxLength="24" value={run.draft.posterTitle[platform]} onChange={e=>saveText('posterTitle',e.target.value)}/></Field><Field label="海报卖点文案"><textarea maxLength="32" value={run.draft.posterLine[platform]} onChange={e=>saveText('posterLine',e.target.value)}/></Field><Field label="海报画面"><select value={run.draft.posterScene[platform]} onChange={e=>{const a=[...run.draft.posterScene];a[platform]=DEMO?+e.target.value:e.target.value;edit({posterScene:a})}}>{DEMO?<><option value="0">清爽背景</option><option value="1">暖色桌面</option><option value="2">浅蓝空间</option></>:<><option value="classic">经典排版</option><option value="product_top">商品置顶</option></>}</select></Field></div>:editor==='copy'?<><div className="three">{run.draft.scripts[platform].map((t,i)=><div key={i}><div className="lineitem">第 {i+1} 镜<span>{DEMO?`${(i*run.duration/3).toFixed(1)}—${((i+1)*run.duration/3).toFixed(1)} 秒`:(shotTiming[i]||'时长待核验')}</span></div><Field label={'第 '+(i+1)+' 镜口播'}><textarea value={t} onChange={e=>{const scripts=clone(run.draft.scripts);scripts[platform][i]=e.target.value;edit({scripts})}}/></Field></div>)}</div><button onClick={()=>open('rewrite',{phase:'request'})}>智能改写</button></>:editor==='image'&&!DEMO?<div className="three">{(run.draft.shots?.[platform]||[]).map((shot,index)=><div key={'shot'+index}><h3>第 {index+1} 镜</h3><Field label={'第 '+(index+1)+' 镜画面'}><select value={shot.video_source_id?'':shot.asset_slot||''} onChange={e=>saveShotPicture(index,{asset_slot:e.target.value})}>{shot.video_source_id&&<option value="" disabled>使用已上传视频</option>}<option value="white">白底图</option><option value="scene_1">场景图一</option><option value="scene_2">场景图二</option></select></Field>{videoSourceAction(shot,index)}{!shot.video_source_id&&repairShotAction(shot,index)}{!shot.video_source_id&&shot.visual_description&&<p>{shot.visual_description}</p>}</div>)}{(run.assets||[]).filter(a=>a.media_kind==='product_image').map(a=><div key={a.id}><h3>{a.slot}</h3><img alt={a.slot+'商品图'} src={'/api/v1/assets/'+encodeURIComponent(a.id)+'/download'} style={{width:'100%'}}/><Tag>{a.review==='approved'?'已采用':a.review==='rejected'?'已拒用':'待复核'}</Tag><button onClick={()=>reviewAsset(a.id,'adopt')}>采用此版本</button><button onClick={()=>reviewAsset(a.id,'reject')}>标记画面有问题</button>{a.review==='rejected'&&<button onClick={()=>open('repair',{assetId:a.id,runKey:idempotencyKey()})}>局部修复</button>}</div>)}</div>:editor==='image'?<div className="three">{run.draft.images.map((n,i)=><div key={i}><h3>第 {i+1} 镜</h3><Art type={run.product.type} scene={n}/><Field label={'第 '+(i+1)+' 镜画面'}><select value={n} onChange={e=>{edit({images:run.draft.images.map((x,j)=>i===j?+e.target.value:x)});patchRun({badShots:(run.badShots||[]).filter(n=>n!==i)})}}><option value="0">原图 · 清爽背景</option><option value="1">场景 · 暖色桌面</option><option value="2">场景 · 浅蓝空间</option></select></Field><button onClick={()=>{patchRun({badShots:[...new Set([...(run.badShots||[]),i])],reviewed:[],status:'待复核'});setToast('画面已标记，请选择其他画面并更新样片')}}>{run.badShots?.includes(i)?'存在问题，待替换':'标记画面有问题'}</button></div>)}</div>:<div className="three">{DEMO?[['配音','voice',['自然女声','沉稳男声','清新女声']],['配乐','music',['轻快日常','舒缓轻音乐','不使用配乐']],['字幕样式','subtitle',['白字深底','黑字浅底']]].map(([n,k,opts])=><Field key={k} label={n}><select value={run.draft[k]} onChange={e=>edit({[k]:e.target.value})}>{opts.map(x=><option key={x}>{x}</option>)}</select></Field>):[
 ['配音','voice',[['Cherry','自然女声 · 芊悦'],['Ethan','清朗男声 · 晨煦'],['Serena','温柔女声 · 苏瑶']]],
 ['配乐','music',[['','不使用配乐'],...(run.product.sources||[]).filter(source=>source.type==='audio'&&source.rights_confirmed).map(source=>[source.id,source.name]),...(run.content.music[platform]&&!(run.product.sources||[]).some(source=>source.id===run.content.music[platform])?[[run.content.music[platform],'当前配乐']]:[])]],
 ['字幕样式','subtitle',[['default','白字深底'],['dark_on_light','黑字浅底'],['large','大字号'],['small','小字号']]],
 ].map(([label,key,choices])=><Field key={key} label={label}><select value={run.draft[key][platform]} onChange={e=>edit({[key]:e.target.value})}>{choices.map(([value,text])=><option key={value} value={value}>{text}</option>)}</select></Field>)}</div>}{!DEMO&&editor==='sound'&&run.sku_id&&<div className="two"><label className="check"><input type="checkbox" checked={musicRights} onChange={e=>setMusicRights(e.target.checked)}/>已确认配乐使用权</label><Field label="上传配乐"><input type="file" accept=".mp3,.wav" disabled={!musicRights||uploadingMusic} onChange={uploadMusic}/></Field></div>}<div className="bottom"><span className="muted">修改自动保存为草稿</span><button className="primary" disabled={!dirty} onClick={()=>open('update')}>应用修改并更新作品</button></div></section>}</>;
 const partialActions=!DEMO&&run?.content&&run.missing_items?.length>0&&<section className="panel">
  <div className="bar"><h2>{creationStatus}</h2><button onClick={()=>nav(4)}>查看任务</button></div>
  <p>{run.missing_items.map(item=>{const [p,kind]=item.split('/');return `${p==='douyin'?'抖音':'小红书'}${kind==='poster'?'海报':'视频'}`}).join('、')}待交付</p>
  {creationTask?.unknown_cost_flag&&<div className="notice">{taskCharges(creationTask).join(' · ')}</div>}
  <div className="bottom">{creationTask?.next_actions.map(action=><button key={action} onClick={()=>action==='cancel'?open('cancel',{task:creationTask}):taskAction(creationTask,action)}>{TASK_ACTION_LABELS[action]}</button>)}</div>
 </section>;
 const repairCandidates=!DEMO&&editor==='image'&&!!run?.repair_candidates?.length&&<section className="panel">
  <h2>修复候选</h2><div className="three">{run.repair_candidates.map(asset=><div key={asset.id}>
   <figure className="source-preview"><img src={'/api/v1/assets/'+encodeURIComponent(asset.id)+'/download'} alt="修复候选"/></figure>
   <Tag>{asset.review==='approved'?'已复核':asset.review==='rejected'?'已拒用':'待复核'}</Tag>
   <button onClick={()=>reviewAsset(asset.id,'adopt')}>通过复核</button>
   <button onClick={()=>reviewAsset(asset.id,'reject')}>拒用</button>
   {asset.review==='approved'&&run.assets?.some(current=>current.id===asset.parent_asset_id)&&
    <button onClick={()=>applyRepair(asset.id)}>应用到当前作品</button>}
  </div>)}</div>
 </section>;
 const workspace=<>{steps}{!run?setup:!run.content||run.status==='更新中'?progress:<>{partialActions}{result}{repairCandidates}</>}</>;
 const listedWorks=DEMO?db.runs:db.runs.filter(w=>db.workListIds?.includes(w.id));
 function listControls(collection,previous,next){
  if(DEMO||(!previous&&!next))return null;
  return <nav aria-label={collection==='works'?'作品分页':'任务分页'} className="actions">
   <button disabled={paging||!previous} onClick={()=>changeListPage(collection,false)}>上一页</button>
   <button disabled={paging||!next} onClick={()=>changeListPage(collection,true)}>下一页</button>
  </nav>;
 }
 const works=<>{listedWorks.length?<div className="grid">{listedWorks.map(workCard)}</div>:<div className="panel empty"><h2>还没有作品</h2><button className="primary" onClick={()=>start()}>开始一键生成</button></div>}{listControls('works',db.workCursors?.length,db.workNext)}</>;
 const tasks= !DEMO ? <section className="panel"><h2>制作任务</h2>{db.tasks?.length?
  <table><thead><tr>{['商品','任务状态','当前阶段','费用','操作'].map(label=><th scope="col" key={label}>{label}</th>)}</tr></thead>
   <tbody>{db.tasks.map(t=>{
    const work=db.runs.find(w=>w.id===t.work_id);
    const state=t.execution_state;
    const status=taskStatus(t);
    return <tr key={t.id}><td>{work?.product.name||(t.work_id?'关联作品':'—')}</td><td><Tag warn={active.includes(status)||status==='部分完成'}>{status}</Tag></td>
     <td>{({creation_run:'视频与海报',edit_run:'更新作品',copy_rewrite:'改写文案',repair_asset:'修复素材'})[t.phase]||t.phase}
      {t.error&&<div role="alert"><b>{t.error.stage}：{t.error.message}</b><p>{t.error.hint}</p></div>}
      {t.video_checks?.map(check=><div key={check.call_id}>供应商视频：{({submitted:'已提交',queued:'排队中',pending:'待处理',processing:'处理中',running:'处理中',succeeded:'已生成',failed:'失败',canceled:'已取消',unknown:'待核查'})[check.status]}</div>)}
     </td><td>{taskCharges(t).map(charge=><div key={charge}>{charge}</div>)}</td>
     <td>{t.work_id&&<button onClick={()=>view({id:t.work_id})}>打开任务</button>}
      {(t.next_actions||[]).map(action=><button key={action} onClick={()=>taskAction(t,action)}>{TASK_ACTION_LABELS[action]||action}</button>)}
     </td></tr>;
   })}</tbody></table>:<div className="empty">暂无制作任务</div>}{listControls('tasks',db.taskCursors?.length,db.taskNext)}</section> : <section className="panel"><h2>制作任务</h2>{db.runs.length?<table><thead><tr><th>商品</th><th>任务状态</th><th>当前阶段</th><th>演示费用</th><th>操作</th></tr></thead><tbody>{db.runs.map(r=><tr key={r.id}><td>{r.product.name}</td><td><Tag warn={active.includes(r.status)}>{r.status}</Tag></td><td>{r.content?'样片第 '+r.revision+' 版':FLOW_STAGES[Math.min(r.stage,3)]}</td><td>{r.unknownReservation?'未知预留 ¥8.00':'已发生 ¥'+r.spent.toFixed(2)}</td><td><button onClick={()=>view(r)}>打开任务</button></td></tr>)}</tbody></table>:<div className="empty">暂无制作任务</div>}<div className="notice">本机演示不产生实际费用。真实任务结果未知时保留费用预留，核查后处理。</div></section>;
 const modalTitles={repair:'局部修复',staticFallback:'选择静图替代',manual:'手工接管文案',generate:'确认本次生成',review:'复核当前作品',rewrite:'智能改写',update:'应用修改',choose:'选择商品',product:'商品资料',new:'新建商品',cancel:'取消后续步骤',unknown:'核查外部结果',facts:'商品事实来源',versions:'历史版本',budget:'调整预算'};
 if(checkingSession)return <div className="auth-page auth-session" role="status">正在连接工作台…</div>;
 if(sessionError)return <div className="auth-page auth-session"><p role="alert">暂时无法连接工作台</p><button onClick={()=>location.reload()}>重新连接</button></div>;
 if(needsLogin)return <AuthScreen onAuthenticated={async()=>{await reloadData();setNeedsLogin(false)}}/>;
 return <><a className="skip" href="#content">跳至主要内容</a><aside><div className="brand"><span className="brandmark"><NavIcon n={0}/></span>映物</div><nav aria-label="主导航">{FLOW_NAMES.map((n,i)=><button key={n} className={page===i?'active':''} aria-current={page===i?'page':undefined} onClick={()=>nav(i)}><FlowNavIcon n={i}/>{n}</button>)}</nav><div className="sidebar-note"><span className="status-dot"></span>{DEMO?'本机交互演示':'营销工作台'}</div><div className="sidebottom"><span className="avatar">林</span><b>林晓</b><span className="muted">商家账号</span></div></aside><main><div id="content" data-screen-label={FLOW_NAMES[page]}><div className="title"><h1>{page===2&&run?.content?'作品详情':FLOW_NAMES[page]}</h1>{page===1?<button className="primary" onClick={()=>open('new')}>新建商品</button>:page!==2?<button className="primary" onClick={()=>start()}>新建创作</button>:run&&<Tag>{run.product.name}</Tag>}</div>{[home,catalog,workspace,works,tasks][page]}</div></main>
 <dialog ref={dialog} aria-labelledby="dialog-title" onCancel={close}><form onSubmit={submit}><div className="bar"><h2 id="dialog-title">{modalTitles[modal?.type]}</h2><button type="button" aria-label="关闭弹窗" onClick={close}>×</button></div>{error&&<div className="error" role="alert">{error}</div>}
 {modal?.type==='manual'&&<>{(DEMO?run.platforms:['douyin','xiaohongshu'].map(p=>modal.task.manual_copy_platforms.includes(p))).map((on,i)=>on&&<section className="review-platform" key={i}><h3>{['抖音','小红书'][i]}</h3><Field label={['抖音','小红书'][i]+'标题'}><input name={'title'+i}/></Field><Field label={['抖音','小红书'][i]+'发布文案'}><textarea name={'body'+i}/></Field>{[0,1,2].map(j=><Field key={j} label={['抖音','小红书'][i]+'第'+(j+1)+'镜口播'}><input name={'shot'+j+i}/></Field>)}{!DEMO&&<><Field label="海报标题"><input name={'posterTitle'+i}/></Field><Field label="海报卖点"><textarea name={'posterPoints'+i}/></Field></>}</section>)}{!DEMO&&<label className="check"><input type="checkbox" name="consent"/>确认使用人工稿继续原任务</label>}</>}
 {modal?.type==='generate'&&<><table><tbody>{[['商品',DEMO?product.name:modal.productName],['平台',(DEMO?['抖音','小红书'].filter((_,i)=>db.prefs.platforms[i]):modal.input.platforms.map(p=>p==='douyin'?'抖音':'小红书')).join('、')],['时长',(DEMO?db.prefs.duration:modal.input.duration_seconds)+' 秒'],['处理内容','营销文案、分镜、画面、配音、字幕、视频合成与海报排版'],['资料与用途','当前已确认商品资料，仅用于本次创作'],['服务商',DEMO?'本地演示，未接入真实服务':Object.values(modal.creationRequest?.quote?.providers||{}).join('、')||'待确认'],['费用上界',DEMO?'¥8.00（本次全部阶段演示值）':modal.creationRequest?.status==='ready'?formatYuan(modal.creationRequest.quote.cost_upper_bound)+'（本次授权上限）':modal.creationRequest||modal.quoteError?'暂无可授权报价':'正在获取报价']].map(([n,v])=><tr key={n}><th>{n}</th><td>{v}</td></tr>)}</tbody></table><label className="check"><input type="checkbox" name="consent" disabled={!DEMO&&modal.creationRequest?.status!=='ready'}/>确认资料处理范围与费用上界</label>{!DEMO&&modal.quoteError&&<p className="notice">{modal.quoteError}</p>}{!DEMO&&modal.creationRequest?.blockers?.map(b=><p className="notice" key={b.code}>{b.message}</p>)}</>}
 {modal?.type==='choose'&&<div className="choose-list">{db.products.map((p,i)=><button type="button" key={p.code} onClick={()=>{setSelected(i);pref('productCode',db.products[i].code);close()}}><span>{p.name} · {p.spec}</span><Tag warn={!p.confirmed}>{p.confirmed?'已确认':'待确认'}</Tag></button>)}</div>}
 {modal?.type==='review'&&<><Field label="导出内容"><select value={modal.exportMode||'完整套件'} onChange={e=>setModal({...modal,exportMode:e.target.value})}><option>完整套件</option><option>仅视频</option><option>仅海报</option></select></Field>{DEMO?modal.exportMode!=='仅海报'&&<div className="three review-images">{run.content.images.map((n,i)=><div key={i}><h3>第 {i+1} 镜</h3><Art type={run.product.type} scene={n}/></div>)}</div>:(!modal.exportMode||modal.exportMode==='完整套件')&&<div className="three review-images">{[['white','白底图'],['scene_1','场景图 1'],['scene_2','场景图 2']].map(([slot,label])=>{const url=previewUrl(run.assets,'product_image',slot);return url&&<div key={slot}><h3>{label}</h3><img src={url} alt={label} className="review-product-image"/></div>})}</div>}{run.platforms.map((on,i)=>on&&<section className="review-platform" key={i}><h3>{['抖音','小红书'][i]}</h3>{modal.exportMode!=='仅视频'&&<div className="review-poster">{DEMO?posterView(run.content,i,true):previewUrl(run.assets,'marketing_poster',['douyin','xiaohongshu'][i])&&<img className="review-poster-image" src={previewUrl(run.assets,'marketing_poster',['douyin','xiaohongshu'][i])} alt="当前海报"/>}</div>}{!DEMO&&modal.exportMode!=='仅海报'&&previewUrl(run.assets,'video',['douyin','xiaohongshu'][i])&&<video className="review-video" controls preload="metadata" src={previewUrl(run.assets,'video',['douyin','xiaohongshu'][i])} aria-label="当前视频"/>}<b>{(DEMO?run.draft:run.content).title[i]}</b><p>{(DEMO?run.draft:run.content).body[i]}</p>{modal.exportMode!=='仅海报'&&<p>{run.content.scripts[i].join(' / ')}</p>}<label className="check"><input type="checkbox" name={'platform'+i}/>已核对{['抖音','小红书'][i]}的{modal.exportMode==='仅海报'?'海报':modal.exportMode==='仅视频'?'视频':'视频与海报'}、商品事实与营销表达</label></section>)}<label className="check"><input type="checkbox" name="rights"/>已核对素材使用权、规格和标识</label>{DEMO&&<div className="notice">当前仅下载演示清单，不含真实媒体或平台发布许可。</div>}</>}
 {!DEMO&&modal?.type==='review'&&run.missing_items?.length>0&&<><Field label="交付类型"><select name="partialMode"><option value="sample">内部样片</option><option value="release">发布包</option></select></Field><Field label="选择已复核的交付文件">
  {(run.assets||[]).filter(a=>a.review==='approved'&&
   (modal.exportMode==='仅视频'?['video','cover','copy'].includes(a.media_kind):
    modal.exportMode==='仅海报'?a.media_kind==='marketing_poster':true))
   .map(a=><label className="check" key={a.id}>
    <input type="checkbox" name="exportAsset" value={a.id}/>
    {({'douyin':'抖音','xiaohongshu':'小红书','white':'白底图','scene_1':'场景图 1','scene_2':'场景图 2'})[a.slot]||a.slot}
    {({'video':'视频','cover':'封面','copy':'文案','marketing_poster':'海报'})[a.media_kind]||''}
   </label>)}
 </Field></>}
 {modal?.type==='staticFallback'&&<><p>仅替代选中的失败动态镜头，原调用费用保留核查。</p>{modal.task.static_fallback_candidates.map(shot=><label className="check" key={shot}><input type="checkbox" name="shots" value={shot}/>{shot}</label>)}<label className="check"><input type="checkbox" name="consent"/>确认使用静图制作这些镜头</label></>}{modal?.type==='update'&&<><table><tbody><tr><th>修改范围</th><td>{[...(!DEMO?['title','body']:[]),'scripts','images','voice','music','subtitle','posterTitle','posterLine','posterScene'].filter(k=>(k==='images'&&shotPictureDirty)||JSON.stringify(run.draft[k])!==JSON.stringify(run.content[k])).map(k=>({title:'发布标题',body:'发布文案',scripts:'口播',images:'画面引用',voice:'配音',music:'配乐',subtitle:'字幕',posterTitle:'海报标题',posterLine:'海报卖点',posterScene:'海报画面'}[k])).join('、')}</td></tr><tr><th>执行影响</th><td>{run.restoreTarget?'恢复所选历史结果，复用全部媒体':textDirty&&!posterDirty&&!videoDirty?'仅更新发布文案，复用全部媒体':posterDirty&&!videoDirty?'仅重排所选平台海报，视频、配音和其他海报全部复用':videoDirty&&!posterDirty?'仅更新受影响视频，已生成海报全部复用':'分别更新受影响视频和海报，复用其余素材'}</td></tr><tr><th>版本</th><td>{DEMO?`建立第 ${run.revision+1} 版，保留第 ${run.revision} 版`:`建立新版本，保留${resultVersionLabel}`}</td></tr><tr><th>费用上界</th><td>{DEMO?'¥2.00（演示）':modal?.remote?.cost_upper_bound!=null?formatYuan(modal.remote.cost_upper_bound):'待服务端报价'}</td></tr></tbody></table><label className="check"><input type="checkbox" name="consent"/>确认修改影响与费用</label><button type="button" onClick={()=>open('budget')}>调整预算上限</button></>}
 {modal?.type==='rewrite'&&!DEMO&&<><label className="check"><input type="checkbox" name="consent"/>确认改写资料处理与费用授权</label>{modal.remote?.items?.map(c=><div className="lineitem" key={c.id}><span>{JSON.stringify(c.changes)}</span><button type="button" onClick={()=>setModal(v=>({...v,candidateId:c.id,phase:'candidate',candidate:JSON.stringify(c.changes)}))}>选择候选</button></div>)}</>}{modal?.type==='rewrite'&&(modal.phase==='candidate'?<><div className="notice">{DEMO?'本地演示候选，未调用模型；采用后才修改草稿。':'采用后才修改草稿，预览保留已合成版本。'}</div><h3>原文</h3><p>{modal.original}</p><h3>新候选</h3><p>{modal.candidate}</p></>:<><Field label="修改内容"><select name="scope"><option>发布文案</option><option>第一镜口播</option></select></Field><Field label="修改方向"><select name="tone"><option>更简洁</option><option>更自然</option></select></Field><Tag>仅修改当前{['抖音','小红书'][platform]}版本</Tag></>)}
 {modal?.type==='versions'&&!DEMO&&<><p>恢复影响整套已选平台，先建立草稿，再应用更新。</p>{modal.remote?.items?.map(v=><div className="lineitem" key={v.id}><span>{v.result_number?`第 ${v.result_number} 版`:`历史结果 ${v.id.slice(0,8)}`}</span><button type="button" onClick={async()=>{try{await request('/works/'+run.id+'/history/'+v.id+'/restore',{method:'POST',body:JSON.stringify({expected_revision:run.revision,platform:['douyin','xiaohongshu'][platform]})});await reloadData();close()}catch(e){setError(e.message)}}}>恢复为新草稿</button></div>)}</>}{modal?.type==='versions'&&DEMO&&<><div className="lineitem">当前样片<Tag>第 {run.revision} 版</Tag></div>{run.history.length?run.history.map((v,i)=><div className="lineitem" key={i}><span>第 {v.revision} 版 · {v.content.title[platform]}</span><button type="button" onClick={()=>{edit({...demoContent(run.product),...clone(v.content)});close();setToast('历史内容已恢复为新草稿，更新样片后生效')}}>恢复为新草稿</button></div>):<div className="empty">首次生成，暂无历史版本</div>}{(run.copyHistory||[]).map((v,i)=><div className="lineitem" key={'draft'+i}><span>改写前人工稿 · 第 {v.revision} 版</span><button type="button" onClick={()=>{edit(clone(v.draft));close();setToast('已恢复改写前人工稿')}}>恢复人工稿</button></div>)}</>}
 {modal?.type==='facts'&&(DEMO?<><div className="lineitem">商品<span>{run.product.name}</span></div><div className="lineitem">规格<span>{run.product.spec}</span></div><div className="lineitem">来源<span>{run.product.files.join('、')}</span></div><div className="notice">本地示例仅使用商品名称与外观。价格、认证、性能数据未经确认，不写入营销文案。</div></>:<>{modal.remote?.items?.length?modal.remote.items.map(fact=><div className="lineitem" key={fact.id}><span>{({name:'商品名称',merchant_sku:'商品编号',specification:'商品规格',product_model:'商品型号'})[fact.id]||fact.id} · {typeof fact.value==='object'?JSON.stringify(fact.value):String(fact.value)}</span><span>{[fact.source_name||(fact.origin==='catalog'?'商品档案':fact.origin==='manual'?'人工确认':'来源未记录'),fact.page!=null?`第 ${fact.page} 页`:null,fact.paragraph!=null?`第 ${fact.paragraph} 段`:null].filter(Boolean).join(' · ')}</span></div>):<div className="empty">{modal.remote?'当前版本没有可显示的事实引用':'正在读取商品事实来源'}</div>}</>)}
 {modal?.type==='product'&&<><Art type={db.products[modal.index].type}/><div className="lineitem">商品<span>{db.products[modal.index].name}</span></div><div className="lineitem">规格<span>{db.products[modal.index].spec}</span></div><div className="lineitem">来源<span>{db.products[modal.index].files.join('、')}</span></div>{!DEMO&&<><label className="check"><input type="checkbox" checked={!!modal.uploadRights} onChange={e=>setModal(v=>({...v,uploadRights:e.target.checked}))}/>我拥有补充素材使用权</label><div className="two"><Field label="商品原图"><select name="product_source" value={modal.previewSources.product} onChange={e=>selectPreviewSource('product',e.target.value)}><option value="">选择原图</option>{(db.products[modal.index].sources||[]).filter(x=>/\.(png|jpe?g)$/i.test(x.name)).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></Field><Field label="商品主体遮罩"><select name="mask_source" value={modal.previewSources.mask} onChange={e=>selectPreviewSource('mask',e.target.value)}><option value="">选择同尺寸遮罩</option>{(db.products[modal.index].sources||[]).filter(x=>/\.(png|jpe?g)$/i.test(x.name)).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></Field></div><div className="two">{[['product','商品原图'],['mask','商品主体遮罩']].map(([role,label])=>{
  const sourceId=modal.previewSources[role];
  return sourceId&&<figure className="source-preview" key={role}>
   <img key={sourceId} src={'/api/v1/sources/'+encodeURIComponent(sourceId)+'/download?inline=true'} alt={label} onLoad={event=>recordPreviewSize(role,sourceId,event)}/>
   {modal.previewSizes?.[role]&&<figcaption>{modal.previewSizes[role]}</figcaption>}
  </figure>
 })}</div>{subjectPreviewUrl(modal)&&<figure className="source-preview subject-preview">
  <img key={subjectPreviewUrl(modal)} src={subjectPreviewUrl(modal)} alt="遮罩保留的商品主体"
   onLoad={()=>setModal(v=>v?.type==='product'&&v.previewSources===modal.previewSources?{...v,subjectPreview:'ready'}:v)}
   onError={()=>setModal(v=>v?.type==='product'&&v.previewSources===modal.previewSources?{...v,subjectPreview:'failed'}:v)}/>
  <figcaption>{modal.subjectPreview==='failed'?'主体预览失败，请检查所选遮罩。':'遮罩保留的商品主体'}</figcaption>
 </figure>}<label className="check" key={JSON.stringify(modal.previewSources)}><input type="checkbox" name="source_reviewed" disabled={modal.subjectPreview!=='ready'}/>已复核遮罩保留真实商品主体</label></>}{DEMO?<Field label="补充商品图片"><input type="file" accept=".png,.jpg,.jpeg" onChange={async e=>{const f=e.target.files[0];if(!f)return;if(f.size>20*1024*1024||!(/\.(png|jpe?g)$/i.test(f.name)))return err('请选择不超过20兆的商品图片');setDb(v=>({...v,products:v.products.map((p,i)=>i===modal.index?{...p,files:[...p.files,f.name]}:p)}))}}/></Field>:<Field label="补充商品资料"><input type="file" accept=".png,.jpg,.jpeg,.pdf,.docx,.txt,.mp4" disabled={!modal.uploadRights||!!modal.uploadingSupplement||!!modal.parsing} onChange={uploadSupplement}/></Field>}<label className="check"><input type="checkbox" name="facts"/>已核对商品外观、规格与事实来源</label></>}
 {!DEMO&&modal?.type==='product'&&<>
  {db.products[modal.index].sources?.filter(source=>source.type==='document').map(source=><div className="lineitem" key={source.id}>
   <span>{source.name} · {modal.parsing===source.id?'解析中':({pending:'待解析',completed:'已解析',awaiting_confirmation:'待核对',partial:'部分可读',failed:'解析失败'})[source.parse_status]||'待解析'}</span>
   <button type="button" disabled={!!modal.parsing} onClick={()=>parseProductDocument(source,db.products[modal.index].id)}>解析资料</button>
  </div>)}
  {modal.documentFacts?.items.map(fact=><label className="check" key={fact.id}>
   <input type={modal.documentFacts.conflicting_keys.includes(fact.key)?'radio':'checkbox'} name={modal.documentFacts.conflicting_keys.includes(fact.key)?'candidate:'+fact.key:'candidate'} value={fact.id}/>
   {fact.key}：{fact.value} · {db.products[modal.index].sources?.find(source=>source.id===fact.source_id)?.name||'商品资料'}
   {fact.locator?.page!=null&&` · 第 ${fact.locator.page} 页`}
  </label>)}
 </>}
 {modal?.type==='new'&&<><Field label="商品名称"><input name="name" readOnly={!!modal.createdSku}/></Field><div className="two"><Field label="商品编号"><input name="code" readOnly={!!modal.createdSku}/></Field><Field label="规格"><input name="spec" readOnly={!!modal.createdSku}/></Field></div><Field label="商品品类"><select name="type"><option>无线耳机</option><option>吹风机</option></select></Field><Field label="商品资料"><input type="file" accept=".png,.jpg,.jpeg,.pdf,.docx,.txt,.mp4" multiple disabled={!!modal.saving} onChange={e=>{const files=Array.from(e.target.files);if(DEMO&&files.some(file=>productUploadError(file)))return err('文件类型不支持或超限：图片20兆、文档30兆、视频200兆。');setModal(v=>({...v,files:files.map(f=>f.name),fileObjects:files,uploadResults:new Map([...(v.uploadResults||[])].filter(([,result])=>result.status!=='failed'))}))}}/></Field>{DEMO?modal.files?.map(n=><div className="lineitem" key={n}>{n}<Tag>仅登记文件名</Tag></div>):
 [...new Set([...(modal.uploadResults?.keys()||[]),...(modal.fileObjects||[])])].map((file,i)=>{
  const outcome=modal.uploadResults?.get(file);
  return <div className="lineitem" key={i}><span>{file.name}{outcome?.message&&<small> · {outcome.message}</small>}</span><Tag warn={outcome?.status==='failed'||outcome?.status==='unknown'}>{({uploaded:'已上传',failed:'上传失败',unknown:'待核对'})[outcome?.status]||'待上传'}</Tag></div>;
 })}<label className="check"><input type="checkbox" name="rights"/>我拥有素材使用权</label></>}
 {modal?.type==='unknown'&&<><div className="notice">暂未取得外部完成或失败证据，保持待核查与 ¥8.00 预留，不重发请求。</div><button type="button" onClick={()=>{patchRun({status:'生成中',stage:3,problem:null,unknownReservation:0});close();setToast('已模拟收到完成证据，复用原请求继续合成')}}>演示收到原请求完成证据</button></>}
 {modal?.type==='cancel'&&<div className="notice">停止尚未提交的步骤。真实外部请求仍可能产生费用，取消不等于退款或释放未知预留。</div>}
 {modal?.type==='repair'&&<><figure className="source-preview"><img src={'/api/v1/assets/'+encodeURIComponent(modal.assetId)+'/download'} alt="待修复画面"/></figure>
 <div className="two">{[['repair_original','回贴原图'],['repair_mask','修复遮罩']].map(([name,label])=><Field key={name} label={label}>
  <select name={name} required onChange={e=>{const id=e.target.value;setModal(v=>({...v,[name]:id}))}}><option value="">选择同尺寸图片</option>
   {(run.product.sources||[]).filter(source=>source.type==='image'&&source.rights_confirmed).map(source=><option value={source.id} key={source.id}>{source.name}</option>)}
  </select>
  {modal[name]&&<img className="review-product-image" alt={label} src={'/api/v1/sources/'+encodeURIComponent(modal[name])+'/download?inline=true'}/>}
 </Field>)}</div></>}
 {modal?.type==='budget'&&<Field label="预算上限（元）"><input type="number" name="budget" defaultValue={run.budget}/></Field>}
 <div className="bottom"><button type="button" onClick={close}>返回</button>{!['choose','versions','facts','unknown'].includes(modal?.type)&&<button className="primary" type="submit" disabled={!DEMO&&((modal?.type==='generate'&&modal.creationRequest?.status!=='ready')||(modal?.type==='product'&&(!modal.documentFacts||!!modal.parsing||!!modal.uploadingSupplement)))}>{({manual:'保存并继续制作',generate:'确认并生成',review:DEMO?'确认并下载演示清单':'确认并下载',rewrite:modal?.phase==='candidate'?'采用候选':'生成改写候选',update:'确认更新样片',product:'确认并创作',new:'保存商品',cancel:'确认取消',budget:'保存预算'})[modal?.type]||'确认'}</button>}</div></form></dialog><div className={'toast '+(toast?'show':'')} role="status">{toast}</div></>;
}
ReactDOM.createRoot(document.getElementById('root')).render(new URLSearchParams(location.search).has('auth-preview')?<AuthScreen preview/>:<FlowApp/>);

