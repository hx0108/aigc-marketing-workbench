import './repair-canvas.css';

const {useRef, useState} = React;

export function maskPoint(rect, width, height, clientX, clientY) {
  return [
    Math.max(0, Math.min(width, (clientX - rect.left) * width / rect.width)),
    Math.max(0, Math.min(height, (clientY - rect.top) * height / rect.height)),
  ];
}

export function RepairCanvas({src, onMask, onSize}) {
  const canvas = useRef(null);
  const mask = useRef(null);
  const active = useRef(null);
  const [ready, setReady] = useState(false);
  const [painted, setPainted] = useState(false);
  const [size, setSize] = useState(5);

  function load(event) {
    const image = event.currentTarget;
    const overlay = canvas.current;
    overlay.width = image.naturalWidth;
    overlay.height = image.naturalHeight;
    const target = document.createElement('canvas');
    target.width = overlay.width;
    target.height = overlay.height;
    target.getContext('2d').fillRect(0, 0, target.width, target.height);
    mask.current = target;
    setReady(true);
    onSize([overlay.width, overlay.height]);
  }

  function stroke(event, previous) {
    const overlay = canvas.current;
    const next = maskPoint(overlay.getBoundingClientRect(), overlay.width, overlay.height, event.clientX, event.clientY);
    const start = previous ?? next;
    for (const [target,color] of [[overlay, '#fa7448'], [mask.current, '#fff']]) {
      const context = target.getContext('2d');
      context.strokeStyle = color;
      context.lineWidth = Math.min(target.width, target.height) * size / 100;
      context.lineCap = 'round';
      context.beginPath();
      context.moveTo(...start);
      context.lineTo(next[0] + 0.01, next[1]);
      context.stroke();
    }
    return next;
  }

  function start(event) {
    if (!ready || event.button !== 0 || active.current) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    active.current = {id:event.pointerId, point:stroke(event)};
    setPainted(true);
    onMask(mask.current);
  }

  function move(event) {
    if (active.current?.id === event.pointerId) active.current.point = stroke(event, active.current.point);
  }

  function end(event) {
    if (active.current?.id === event.pointerId) active.current = null;
  }

  function clear() {
    const overlay = canvas.current;
    overlay.getContext('2d').clearRect(0, 0, overlay.width, overlay.height);
    const target = mask.current;
    const context = target.getContext('2d');
    context.fillStyle = '#000';
    context.fillRect(0, 0, target.width, target.height);
    setPainted(false);
    onMask(null);
  }

  return <div className="repair-canvas">
    <div className="repair-canvas-preview">
      <img src={src} onLoad={load} onError={()=>{setReady(false);onMask(null)}} alt="待修复画面"/>
      <canvas ref={canvas} onPointerDown={start} onPointerMove={move}
        onPointerUp={end} onPointerCancel={end} onLostPointerCapture={end} aria-label="绘制局部修复区域"/>
    </div>
    <div className="repair-canvas-tools">
      <label>画笔大小 <input type="range" min="1" max="20" value={size} onChange={event=>setSize(Number(event.target.value))}/></label>
      <button type="button" disabled={!painted} onClick={clear}>清除标记</button>
    </div>
  </div>;
}
