import './creation-preview.css';

const channels = {douyin: '抖音', xiaohongshu: '小红书'};

export function CreationPreview({creation, media, headline}) {
  const photos = creation.photo_sources
    ? creation.photo_sources.map(({source_id}) => media.find(photo => photo.id === source_id) || {id: source_id})
    : media;
  const main = photos.find(photo => photo.id === creation.wear_source_id) || photos[0];
  const labels = {
    scene: creation.wear_source_id ? '佩戴场景' : '商品场景',
    packshot: '商品特写',
    end: '收尾',
  };

  return <section className="creation-preview" aria-label="生成前预览">
    <h3>生成前预览</h3>
    {headline && <p>海报标题　{headline}</p>}
    <div className="creation-preview-photos">
      {photos.map((photo, index) => <figure key={photo.id}>
        <img src={'/api/v1/sources/' + encodeURIComponent(photo.id) + '/download?inline=true'}
             alt={photo.name || '商品参考图 ' + (index + 1)} />
        <figcaption>{photo.id === main?.id ? '主参考图' : '商品参考图'}</figcaption>
      </figure>)}
    </div>
    {creation.storyboards ? Object.entries(creation.storyboards).map(([channel, shots]) =>
      <div key={channel}>
        <h4>{channels[channel]}</h4>
        <ol className="creation-preview-shots">
          {shots.map(({view, seconds}) => <li key={view}>
            <span>{labels[view] || photos.find(photo => photo.id === view)?.name || '其他商品角度'}</span>
            <span>{seconds.toFixed(2).replace(/\.?0+$/, '')} 秒</span>
          </li>)}
        </ol>
      </div>) : <>
      {creation.brief && <p>创意要求　{creation.brief}</p>}
      <p>授权后生成分镜和画面。</p>
    </>}
  </section>;
}
