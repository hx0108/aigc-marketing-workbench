export function previewUrl(assets = [], kind, platform) {
  const asset = assets.find(a => a.media_kind === kind && a.slot === platform);
  return asset ? `/api/v1/assets/${encodeURIComponent(asset.id)}/download` : null;
}

export function shotTimeLabels(shots = []) {
  let cursor = 0;
  const format = value => Number.isInteger(value) ? value.toFixed(1) : String(value);
  return shots.map(shot => {
    const value = shot?.duration;
    const duration = (typeof value === 'number' || typeof value === 'string' && value.trim()) ? Number(value) : NaN;
    if (cursor === null || !Number.isFinite(duration) || duration <= 0) {
      cursor = null;
      return '时长待核验';
    }
    const start = cursor;
    cursor = Math.round((cursor + duration) * 1e6) / 1e6;
    return `${format(start)}—${format(cursor)} 秒`;
  });
}

export function workbenchLocation(hash) {
  const [section, query] = hash.slice(1).split('?', 2);
  const page = /^[0-4]$/.test(section) ? Number(section) : 0;
  return {page, workId: page === 2 ? new URLSearchParams(query).get('work') || null : null};
}

export function hasActiveTasks(tasks, workId) {
  return tasks.some(task => (!workId || task.work_id === workId) &&
    (task.execution_state === 'queued' || task.execution_state === 'running'));
}

export function listPagePath(collection, cursor) {
  const query = new URLSearchParams({order: 'created_desc'});
  if (cursor) query.set('cursor', cursor);
  return `/${collection}?${query}`;
}

export function exportError(detail) {
  const code = typeof detail?.code === 'string' ? detail.code.split(':', 1)[0] : '';
  return ({
    RULESET_UNVERIFIED: '平台发布规则尚未核验，可下载内部样片。',
    RULESET_INVALID: '平台发布规则配置无效，可下载内部样片。',
    RULESET_EXPIRED: '平台发布规则已过期，可下载内部样片。',
    RULESET_PLATFORM_MISSING: '所选平台缺少已核验的发布规则。',
    RULESET_SPEC_MISSING: '发布规则缺少此类文件的规格。',
    LABEL_VERIFICATION_REQUIRED: '发布文件的 AI 标识尚未核验。',
    MATERIAL_RIGHTS_UNVERIFIED: '商品素材或配乐的使用权尚未确认。',
    FACT_REVOKED: '商品档案已失效，请重新确认。',
    MEDIA_SPEC_MISMATCH: '文件规格与平台发布规则不符。',
    REVIEW_REQUIRED: '请先复核所选文件。',
    ASSET_REJECTED: '所选文件含已拒用版本，请替换后再导出。',
    REPAIR_SOURCE_REVIEW_REQUIRED: '作品引用的修复图未通过复核，请复核该图或替换后重制。',
    ASSET_REVIEW_CHANGED: '文件复核状态已变化，请重新打开复核弹窗。',
    INCOMPLETE_SELECTION: '所选套件还有缺失文件，请选择已完成的部分。',
    MEDIA_NOT_AVAILABLE: '当前没有可导出的文件。',
  })[code] || '导出失败，请稍后重试。';
}

export function assetsForExport(assets, selection) {
  if (selection === 'full_suite') return assets.filter(asset =>
    ['video', 'cover', 'copy', 'marketing_poster', 'product_image'].includes(asset.media_kind));
  const kinds = selection === 'poster_only' ? ['marketing_poster'] : ['video', 'cover', 'copy'];
  return assets.filter(asset => kinds.includes(asset.media_kind));
}

export function productUploadError(file) {
  const extension = file.name.toLowerCase().match(/\.([a-z0-9]+)$/)?.[1];
  const limits = {png:20,jpg:20,jpeg:20,pdf:30,docx:30,txt:30,mp4:200};
  if (!Object.hasOwn(limits,extension)) return '文件格式不支持。';
  const limit = limits[extension];
  if (!file.size) return '文件为空。';
  if (file.size > limit * 1024 * 1024) return `文件超过 ${limit} MB。`;
  return null;
}

export function taskCharges(task) {
  const charges = [];
  for (const [key, label] of [
    ['settled_cost', '已结算'],
    ['reserved_cost', task.unknown_cost_flag ? '待核查预留' : '未结算预留'],
  ]) {
    const amount = formatYuan(task[key]);
    if (!amount || amount === '¥0.00') continue;
    charges.push(`${label} ${amount}`);
  }
  return charges.length ? charges : ['¥0.00'];
}

export function formatYuan(value) {
  const amount = String(value ?? '');
  if (!/^\d+(?:\.\d+)?$/.test(amount)) return null;
  const [whole, fraction = ''] = amount.split('.');
  return `¥${whole}.${fraction.replace(/0+$/, '').padEnd(2, '0')}`;
}

export function workStatusLabel(status) {
  return ({queued:'待开始',running:'生成中',paused:'已暂停',awaiting_review:'待复核',
    approved:'已复核',partial:'部分完成',failed:'生成失败',external_unknown:'结果待核查（已停止推进）',
    recovery_required:'待核查',canceled:'已取消'})[status] || status;
}
export function resultContent(copy = {}, draft = {}, renderSettings = {}) {
  const result = {title:[],body:[],scripts:[],shots:[],posterTitle:[],posterLine:[],posterScene:[],images:[],voice:[],music:[],subtitle:[]};
  ['douyin','xiaohongshu'].forEach((platform,i) => {
    const c = {...(copy[platform] || {}), ...(draft.platform === platform ? draft : {})};
    const baseShots=(copy[platform]?.shots || []).map((shot,index)=>{
      const source=renderSettings[platform]?.shot_video_sources?.[index];
      return {asset_slot:renderSettings[platform]?.poster_scene || 'scene_1',...shot,
        ...(source?{video_source_id:source.source_id,start_seconds:source.start_seconds}:{})};
    });
    if(draft.platform===platform)for(const {index,...patch} of draft.shots || [])if(baseShots[index]){
      const shot={...baseShots[index],...patch};
      if (!patch.video_source_id && ['asset_slot','repair_asset_id','visual_description'].some(key=>key in patch)){
        delete shot.video_source_id;
        delete shot.start_seconds;
      }
      baseShots[index]=shot;
    }
    result.shots[i]=baseShots;
    result.title[i]=c.title || ''; result.body[i]=c.body || '';
    result.scripts[i]=baseShots.length?baseShots.map(s=>s.narration):(Array.isArray(c.narration)?c.narration:[c.narration || '']);
    result.posterTitle[i]=c.poster_title || '';
    result.posterLine[i]=Array.isArray(c.poster_points || c.selling_points)?(c.poster_points || c.selling_points).join(' · '):(c.poster_points || c.selling_points || '');
    result.posterScene[i]=(draft.platform === platform ? draft.poster_layout : null) || renderSettings[platform]?.poster_layout || 'classic';
    const settings={...renderSettings[platform],...(draft.platform===platform?draft:{})};
    result.voice[i]=settings.voice || 'Cherry';
    result.music[i]=settings.music || '';
    result.subtitle[i]=settings.subtitle_style || 'default';
  });
  return result;
}
export function narrationPatch(previous,next,platform){
 return {platform,shots:next.flatMap((narration,index)=>narration===previous[index]?[]:[{index,narration}])};
}

export function creationQuoteError(error){
 const messages={PROFILE_INCOMPLETE:'商品资料未完整，请返回商品档案补充并确认。',PROFILE_NOT_CONFIRMED:'请先确认商品档案。',SOURCE_SCOPE_INVALID:'商品资料来源已失效，请重新选择资料。',FACT_CONFLICT:'商品事实存在冲突，请返回档案核对。',FACT_CONFLICT_UNRESOLVED:'商品事实冲突尚未处理，请先核对。',FACT_REQUIRED:'请先填写商品事实。',FACT_SOURCE_REQUIRED:'请先补充商品事实来源。'};
 if(messages[error?.detail?.code])return messages[error.detail.code];
 if(error?.status===401)return '登录已失效，请重新登录。';
 if(error?.status===422)return '创作参数不完整或格式不正确，请检查后重试。';
 if(error?.message==='服务返回无效响应')return error.message;
 return '无法获取本次报价，请关闭后重试。';
}
