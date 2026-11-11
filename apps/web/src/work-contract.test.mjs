import {test} from 'node:test';
import assert from 'node:assert/strict';
import {productUploadError} from './work-contract.mjs';
import {shotTimeLabels} from './work-contract.mjs';

test('shot timing follows actual single, uneven and multi-shot plans',()=>{
 assert.deepEqual(shotTimeLabels([{duration:6}]),['0.0—6.0 秒']);
 assert.deepEqual(shotTimeLabels([{duration:7},{duration:13},{duration:27}]),['0.0—7.0 秒','7.0—20.0 秒','20.0—47.0 秒']);
 assert.deepEqual(shotTimeLabels([1,2,3,4].map(duration=>({duration}))),['0.0—1.0 秒','1.0—3.0 秒','3.0—6.0 秒','6.0—10.0 秒']);
 assert.deepEqual(shotTimeLabels([{duration:'0.25'},{duration:1.75}]),['0.0—0.25 秒','0.25—2.0 秒']);
 assert.deepEqual(shotTimeLabels([{duration:2},{},{duration:3}]),['0.0—2.0 秒','时长待核验','时长待核验']);
});

test('individual upload validation handles unsupported, empty and oversized files',()=>{
 assert.equal(productUploadError({name:'sku.PNG',size:20*1024*1024}),null);
 assert.equal(productUploadError({name:'sku.PNG',size:20*1024*1024+1}),'文件超过 20 MB。');
 assert.equal(productUploadError({name:'spec.txt',size:0}),'文件为空。');
 assert.equal(productUploadError({name:'other.constructor',size:1}),'文件格式不支持。');
});
import {previewUrl,resultContent,narrationPatch,workbenchLocation,taskCharges,hasActiveTasks,listPagePath,assetsForExport,exportError,formatYuan} from './work-contract.mjs';

test('quote formats cents without rounding away finer precision',()=>{
 assert.equal(formatYuan('10.00000000'),'¥10.00');
 assert.equal(formatYuan('0.00000001'),'¥0.00000001');
});

test('poster controls preserve saved platform layouts and show the current draft',()=>{
 const settings={douyin:{poster_layout:'product_top'}};
 assert.deepEqual(resultContent({}, {}, settings).posterScene,['product_top','classic']);
 assert.deepEqual(resultContent({}, {platform:'xiaohongshu',poster_layout:'product_top'}, settings).posterScene,['product_top','product_top']);
});

test('audio settings preserve provider voice IDs and only patch the selected platform',()=>{
 const settings={douyin:{voice:'Ethan',music:'licensed-audio'},xiaohongshu:{voice:'Serena',subtitle_style:'dark_on_light'}};
 const draft=resultContent({}, {platform:'douyin',music:'',subtitle_style:'dark_on_light'}, settings);
 assert.deepEqual(draft.voice,['Ethan','Serena']);
 assert.deepEqual(draft.music,['','']);
 assert.deepEqual(draft.subtitle,['dark_on_light','dark_on_light']);
 assert.deepEqual(resultContent({}, {}, settings).music,['licensed-audio','']);
});

test('poster review scopes adoption to posters and explains a missing ruleset',()=>{
 const assets=[{media_kind:'marketing_poster',id:'poster'},{media_kind:'video',id:'video'}];
 assert.deepEqual(assetsForExport(assets,'poster_only').map(asset=>asset.id),['poster']);
 assert.match(exportError({code:'RULESET_UNVERIFIED'}),/可下载内部样片/);
 assert.match(exportError({code:'INCOMPLETE_SELECTION:video/douyin'}),/缺失文件/);
});

test('list pages preserve sort and encode the API cursor without offset',()=>{
 assert.equal(listPagePath('works'),'/works?order=created_desc');
 assert.equal(listPagePath('tasks','a+b/='),'/tasks?order=created_desc&cursor=a%2Bb%2F%3D');
});

test('live progress follows the selected work and stops on pause or terminal state',()=>{
 const tasks=[{work_id:'a',execution_state:'paused'},{work_id:'b',execution_state:'queued'},
  {work_id:'a',execution_state:'external_unknown'}];
 assert.equal(hasActiveTasks(tasks,null),true);
 assert.equal(hasActiveTasks(tasks,'a'),false);
 assert.equal(hasActiveTasks(tasks,'b'),true);
 assert.equal(hasActiveTasks([{work_id:'b',execution_state:'succeeded'}],'b'),false);
});

test('a work deep link preserves the selected result after a reload',()=>{
 assert.deepEqual(workbenchLocation('#2?work=work%3A123'),{page:2,workId:'work:123'});
 assert.deepEqual(workbenchLocation('#4?work=unrelated'),{page:4,workId:null});
 assert.deepEqual(workbenchLocation('#2'),{page:2,workId:null});
});

test('task fees distinguish settled cost from an unknown reservation',()=>{
 assert.deepEqual(taskCharges({settled_cost:'1.25000000',reserved_cost:'0.00000001',unknown_cost_flag:true}),
  ['已结算 ¥1.25','待核查预留 ¥0.00000001']);
 assert.deepEqual(taskCharges({settled_cost:'0E-8',reserved_cost:'2.00'}),['未结算预留 ¥2.00']);
});
test('worker asset contract chooses exact media kind and platform, never storage object key',()=>{
 const assets=[{id:'rev:video:douyin',media_kind:'video',slot:'douyin',object_key:'private.mp4'},{id:'poster',media_kind:'marketing_poster',slot:'xiaohongshu'}];
 assert.equal(previewUrl(assets,'video','douyin'),'/api/v1/assets/rev%3Avideo%3Adouyin/download');
 assert.equal(previewUrl(assets,'video','xiaohongshu'),null);
 assert.equal(previewUrl(assets,'marketing_poster','xiaohongshu'),'/api/v1/assets/poster/download');
});
test('single shot edits preserve unchanged shots and rendered source',()=>{
 const copy={douyin:{shots:[{narration:'A',asset_slot:'white'},{narration:'B',asset_slot:'scene_1'}]}};
 const patch=narrationPatch(['A','B'],['A','new'],'douyin');
 assert.deepEqual(patch,{platform:'douyin',shots:[{index:1,narration:'new'}]});
 const draft=resultContent(copy,patch);
 assert.deepEqual(draft.scripts[0],['A','new']);assert.equal(draft.shots[0][1].asset_slot,'scene_1');
 assert.equal(copy.douyin.shots[1].narration,'B');
});
test('uploaded video selection survives refresh and can be replaced by its prior image',()=>{
 const copy={douyin:{shots:[{duration:2,asset_slot:'white'},{duration:2,asset_slot:'scene_2'}]}};
 const settings={douyin:{shot_video_sources:{0:{source_id:'video-a',start_seconds:1.25}}}};
 assert.equal(resultContent(copy,{},settings).shots[0][0].video_source_id,'video-a');
 const draft=resultContent(copy,{platform:'douyin',shots:[{index:0,asset_slot:'white'},
  {index:1,video_source_id:'video-b',start_seconds:0}]},settings);
 assert.equal(draft.shots[0][0].video_source_id,undefined);
 assert.equal(draft.shots[0][1].video_source_id,'video-b');
 assert.equal(draft.shots[0][1].start_seconds,0);
});
test('draft affects selected platform only and leaves rendered content immutable',()=>{
 const copy={douyin:{title:'original',shots:[{narration:'rendered'}],selling_points:['A','B']},xiaohongshu:{title:'other'}};
 const rendered=resultContent(copy),draft=resultContent(copy,{platform:'douyin',title:'edited'});
 assert.equal(rendered.shots[0][0].asset_slot,'scene_1');
 assert.equal(resultContent(copy,{}, {douyin:{poster_scene:'scene_2'}}).shots[0][0].asset_slot,'scene_2');
 assert.equal(rendered.title[0],'original');assert.equal(draft.title[0],'edited');assert.equal(draft.title[1],'other');
 assert.equal(rendered.posterLine[0],'A · B');assert.deepEqual(rendered.scripts[0],['rendered']);assert.equal(copy.douyin.title,'original');
});
