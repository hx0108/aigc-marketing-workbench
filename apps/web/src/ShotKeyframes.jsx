const {useState} = React;

export function ShotKeyframes({assets, index, shot, onSave}) {
  const candidates = assets.filter(asset => asset.media_kind === 'product_image' && asset.review === 'approved');
  const [first, setFirst] = useState(shot.first_frame_asset_id || '');
  const [last, setLast] = useState(shot.last_frame_asset_id || '');
  const [saving, setSaving] = useState(false);
  const firstAsset = candidates.find(asset => asset.id === first);
  const lastAsset = candidates.find(asset => asset.id === last);
  const changed = first !== (shot.first_frame_asset_id || '') || last !== (shot.last_frame_asset_id || '');
  const conflict = shot.video_source_id || shot.repair_asset_id || shot.motionRequested;

  async function save(frames) {
    setSaving(true);
    try {
      await onSave(index, frames);
    } finally {
      setSaving(false);
    }
  }

  function frame(label, value, change, asset, other) {
    return <div className="keyframe-pick">
      <label className="field">{label}
        <select value={value} onChange={event=>change(event.target.value)} disabled={saving}>
          <option value="">选择已采用的图片</option>
          {candidates.map((option, position)=><option key={option.id} value={option.id} disabled={other===option.id}>
            {option.name || ({white:'白底图',scene_1:'场景图一',scene_2:'场景图二'})[option.slot] || '商品图'} · {position+1}
          </option>)}
        </select>
      </label>
      {asset && <img src={'/api/v1/assets/'+encodeURIComponent(asset.id)+'/download'} alt={label+'预览'} />}
    </div>;
  }

  return <details className="shot-keyframes" open={shot.first_frame_asset_id ? true : undefined}>
    <summary>首尾帧</summary>
    {conflict ? <p>此镜头已选择其他生成方式，请先取消该方式。</p> :
      candidates.length < 2 ? <p>在下方先采用两张商品图，即可选择首帧和尾帧。</p> : <>
        <div className="two">
          {frame('首帧',first,setFirst,firstAsset,last)}
          {frame('尾帧',last,setLast,lastAsset,first)}
        </div>
        <button type="button" disabled={saving || !changed || !firstAsset || !lastAsset || first===last}
          onClick={()=>save({first_frame_asset_id:first,last_frame_asset_id:last})}>保存首尾帧</button>
      </>}
    {shot.first_frame_asset_id && <button type="button" disabled={saving}
      onClick={()=>save({first_frame_asset_id:null,last_frame_asset_id:null})}>清除首尾帧设置</button>}
  </details>;
}
