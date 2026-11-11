const {
  useState,
  useEffect,
  useRef
} = React;
const pages = ['工作台', '商品档案', '一键出片', '创作方案', '素材与分镜', '我的作品', '任务中心'];
const iconPaths = ['M4 10 12 3l8 7M6 9v11h12V9', 'M5 7 12 3l7 4v10l-7 4-7-4zM5 7l7 4 7-4M12 11v10', 'M4 7h16M7 4v6M4 17h16M16 14v6', 'M5 5h14v14H5M9 9h6M9 13h4', 'M5 4h14v16H5zM5 16l5-5 4 4 3-3 2 2', 'M8 5 19 12 8 19z', 'M6 5h12M6 12h12M6 19h8'];
const seed = {
  products: [{
    name: '轻音无线耳机',
    spec: '雾白 · 单规格',
    code: '1001',
    confirmed: true,
    type: 0,
    files: ['商品正面图', '产品说明书'],
    version: 2
  }, {
    name: '轻风高速吹风机',
    spec: '暖砂 · 单规格',
    code: '1002',
    confirmed: false,
    type: 1,
    files: ['商品正面图', '参数说明'],
    version: 1
  }, {
    name: '随行无线耳机',
    spec: '岩灰 · 单规格',
    code: '1003',
    confirmed: true,
    type: 0,
    files: ['商品正面图'],
    version: 1
  }],
  current: 0,
  settings: {
    platforms: [true, false],
    duration: '15',
    audience: '城市通勤人群',
    goal: '商品卖点展示',
    method: '原图合成与场景生成',
    budget: 30,
    brief: '突出轻巧便携与通勤场景，保留商品真实外观。'
  },
  scripts: [['通勤路上，给自己留一点空间。', '轻巧入袋，随取随听。', '让音乐陪你，轻装出发。'], ['出门前，装好今天的小小快乐。', '圆润机身，放进口袋刚刚好。', '选一首喜欢的歌，开始今天的旅程。']],
  plan: 1,
  history: [],
  repairSpent: 0,
  authorized: false,
  generated: false,
  assets: [{
    name: '白底图',
    state: '待复核',
    version: 1
  }, {
    name: '通勤场景',
    state: '待复核',
    version: 1
  }, {
    name: '桌面场景',
    state: '待复核',
    version: 1
  }],
  checks: [false, false, false],
  canceled: false,
  failed: true,
  videoVersion: 1,
  title: ['通勤路上，轻装出发', '口袋里的通勤搭子'],
  subtitle: '白字 · 底部居中',
  exports: [true, true, false, true]
};
const solidIcons = ["<rect x=\"3\" y=\"3\" width=\"8\" height=\"8\" rx=\"2.5\"/><rect x=\"14\" y=\"3\" width=\"7\" height=\"7\" rx=\"2.5\"/><rect x=\"3\" y=\"14\" width=\"7\" height=\"7\" rx=\"2.5\"/><circle cx=\"17\" cy=\"17\" r=\"4\"/>", "<path d=\"M8 3h8l2 4H6zM5 8h14a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2\"/><path d=\"M9 12h6\" stroke=\"white\" stroke-width=\"2\"/>", "<rect x=\"3\" y=\"5\" width=\"18\" height=\"3\" rx=\"1.5\"/><circle cx=\"15\" cy=\"6.5\" r=\"4\"/><rect x=\"3\" y=\"16\" width=\"18\" height=\"3\" rx=\"1.5\"/><circle cx=\"8\" cy=\"17.5\" r=\"4\"/>", "<path d=\"m4 16-1 6 6-1L19 11l-5-5zM16 4l2-2a2 2 0 0 1 3 3l-2 2z\"/>", "<rect x=\"3\" y=\"4\" width=\"18\" height=\"17\" rx=\"4\"/><circle cx=\"16\" cy=\"9\" r=\"2\" fill=\"white\"/><path d=\"m5 18 5-6 4 4 3-2 3 4\" fill=\"white\"/>", "<rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"5\"/><path d=\"m10 8 6 4-6 4z\" fill=\"white\"/>", "<rect x=\"3\" y=\"3\" width=\"18\" height=\"19\" rx=\"4\"/><path d=\"M8 8h8M8 12h8M8 16h5\" stroke=\"white\" stroke-width=\"2\"/>"];
function NavIcon({
  n
}) {
  return React.createElement("svg", {
    className: "navicon solid-icon",
    viewBox: "0 0 24 24",
    "aria-hidden": "true",
    dangerouslySetInnerHTML: {
      __html: solidIcons[n]
    }
  });
}
function I({
  n = 0
}) {
  return React.createElement("svg", {
    className: "navicon",
    viewBox: "0 0 24 24",
    "aria-hidden": "true"
  }, React.createElement("path", {
    d: iconPaths[n]
  }));
}
function Tag({
  children,
  warn = false
}) {
  return React.createElement("span", {
    className: 'tag ' + (warn ? 'warn' : '')
  }, children);
}
function Art({
  type = 0,
  scene = 0,
  small = false
}) {
  return React.createElement("div", {
    className: 'art scene' + scene + (small ? ' small' : ''),
    role: "img",
    "aria-label": type ? '吹风机设计示意' : '耳机设计示意'
  }, React.createElement("div", {
    className: "orb"
  }), React.createElement("div", {
    className: type ? 'dryer' : 'product'
  }, React.createElement("span", null)), React.createElement("div", {
    className: "plinth"
  }));
}
function Field({
  label,
  children
}) {
  return React.createElement("label", {
    className: "field"
  }, label, children);
}
const flowNavShapes = ['<path d="M10.2 3a3 3 0 0 1 3.6 0l7 5.5a1.5 1.5 0 0 1-.9 2.7H19V19a2 2 0 0 1-2 2h-3v-6h-4v6H7a2 2 0 0 1-2-2v-7.8h-.9a1.5 1.5 0 0 1-.9-2.7z"/>', '<path d="m12 2 9 4.5-9 4.5L3 6.5zM3 9l8 4v9l-7-3.5a2 2 0 0 1-1-1.8zm10 4 8-4v8.7a2 2 0 0 1-1 1.8L13 22z"/>', '<rect x="3" y="2" width="12" height="15" rx="3"/><rect x="7" y="9" width="15" height="12" rx="3" stroke="white" stroke-width="1.5"/><path d="m13 12 5 3-5 3z" fill="white"/>', '<path d="M3 6a3 3 0 0 1 3-3h4l3 3h5a3 3 0 0 1 3 3v1H3zM2 12h20l-1.6 7a3 3 0 0 1-3 2H6.6a3 3 0 0 1-3-2z"/>', '<rect x="3" y="3" width="18" height="19" rx="4"/><path d="m7 9 1.5 1.5L11 8m-4 8 1.5 1.5L11 15M14 9h3m-3 7h3" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'];
function FlowNavIcon({
  n
}) {
  return React.createElement("svg", {
    className: "navicon solid-icon",
    viewBox: "0 0 24 24",
    "aria-hidden": "true",
    dangerouslySetInnerHTML: {
      __html: flowNavShapes[n]
    }
  });
}
const FLOW_KEY = 'marketing-flow-v4';
const FLOW_NAMES = ['创作首页', '商品资料', '视频与海报', '作品管理', '生成任务'];
const FLOW_STAGES = ['创作文案', '编排画面', '配音与字幕', '视频与海报'];
const clone = v => JSON.parse(JSON.stringify(v));
function demoContent(p, style = '自然介绍') {
  return {
    posterTitle: [p.name + '，日常新灵感', p.name + '的日常搭配'],
    posterLine: ['从真实细节出发，选择适合自己的好物', '把日常好物，放进喜欢的生活'],
    posterScene: [0, 2],
    title: [p.name + '，日常新灵感', p.name + '的日常分享'],
    body: ['从外观与细节认识' + p.name + '，选购前请核对商品规格。', '今天分享' + p.name + '，从真实外观开始，找到适合自己的选择。'],
    scripts: [['看看这件日常好物。', '从细节了解' + p.name + '。', '选购前，核对适合自己的规格。'], ['今天的日常分享，从这里开始。', '一起看看' + p.name + '的外观。', '根据自己的需要，选择合适的商品。']],
    images: [0, 1, 2],
    voice: '自然女声',
    music: '轻快日常',
    subtitle: '白字深底',
    style
  };
}
function initialFlow() {
  try {
    const saved = JSON.parse(localStorage.getItem(FLOW_KEY));
    if (saved) {
      saved.runs = saved.runs.map(r => {
        const d = demoContent(r.product);
        return {
          ...r,
          content: r.content ? {
            ...d,
            ...r.content
          } : r.content,
          draft: r.draft ? {
            ...d,
            ...r.draft
          } : r.draft
        };
      });
      return saved;
    }
    const old = JSON.parse(localStorage.getItem('marketing-prototype-v3'));
    const products = old?.products || seed.products;
    const pref = old?.settings || seed.settings;
    const migrated = [];
    if (old?.generated) {
      const content = {
        ...demoContent(products[old.current || 0]),
        title: old.title,
        scripts: old.scripts,
        body: old.copyBody || ['', ''],
        subtitle: old.subtitle?.startsWith('黑') ? '黑字浅底' : '白字深底'
      };
      migrated.push({
        id: 'legacy-' + Date.now(),
        product: clone(products[old.current || 0]),
        platforms: pref.platforms,
        duration: +pref.duration,
        status: '待复核',
        stage: 4,
        content: clone(content),
        draft: clone(content),
        revision: 1,
        reviewed: [],
        history: [],
        spent: 0,
        budget: pref.budget,
        created: Date.now(),
        legacy: true
      });
    }
    return {
      products,
      prefs: {
        platforms: pref.platforms,
        duration: pref.duration,
        budget: pref.budget,
        brief: ''
      },
      runs: migrated,
      current: null
    };
  } catch {
    return {
      products: clone(seed.products),
      prefs: {
        platforms: [true, false],
        duration: '15',
        budget: 30,
        brief: ''
      },
      runs: [],
      current: null
    };
  }
}
function FlowApp() {
  const [db, setDb] = useState(initialFlow),
    [page, setPage] = useState(() => Math.max(0, Math.min(4, +location.hash.slice(1) || 0))),
    [selected, setSelected] = useState(() => Math.max(0, db.products.findIndex(p => p.code === db.prefs.productCode))),
    [platform, setPlatform] = useState(0),
    [editor, setEditor] = useState(''),
    [mediaMode, setMediaMode] = useState('视频'),
    [modal, setModal] = useState(null),
    [error, setError] = useState(''),
    [toast, setToast] = useState(''),
    [query, setQuery] = useState(''),
    [filter, setFilter] = useState('全部'),
    [playing, setPlaying] = useState(false),
    [time, setTime] = useState(0),
    [scenario, setScenario] = useState('正常生成');
  const dialog = useRef(null),
    focusBefore = useRef(null);
  const run = db.runs.find(x => x.id === db.current),
    product = db.products[selected] || db.products[0];
  const dirty = !!run && JSON.stringify({
    ...run.draft,
    title: [],
    body: []
  }) !== JSON.stringify({
    ...run.content,
    title: [],
    body: []
  });
  const posterDirty = !!run && ['posterTitle', 'posterLine', 'posterScene'].some(k => JSON.stringify(run.draft?.[k]) !== JSON.stringify(run.content?.[k]));
  const videoDirty = !!run?.content && ['scripts', 'images', 'voice', 'music', 'subtitle'].some(k => JSON.stringify(run.draft[k]) !== JSON.stringify(run.content[k]));
  const active = ['生成中', '已暂停', '待处理', '待核查', '更新中'];
  useEffect(() => {
    try {
      localStorage.setItem(FLOW_KEY, JSON.stringify(db));
    } catch {
      setToast('本机保存失败，请勿关闭页面');
    }
  }, [db]);
  useEffect(() => {
    if (modal) {
      focusBefore.current = document.activeElement;
      dialog.current.showModal();
    } else if (dialog.current?.open) {
      dialog.current.close();
      focusBefore.current?.focus();
    }
  }, [!!modal]);
  useEffect(() => {
    const f = () => {
      if (location.hash !== '#content') setPage(Math.max(0, Math.min(4, +location.hash.slice(1) || 0)));
    };
    addEventListener('hashchange', f);
    return () => removeEventListener('hashchange', f);
  }, []);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(''), 2800);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    if (!playing || !run) return;
    const t = setInterval(() => setTime(v => {
      if (v >= run.duration) {
        setPlaying(false);
        return 0;
      }
      return v + 1;
    }), 1000);
    return () => clearInterval(t);
  }, [playing, run?.id]);
  useEffect(() => {
    setPlaying(false);
    setTime(0);
    setEditor('');
    if (run) setPlatform(run.platforms[0] ? 0 : 1);
  }, [run?.id, page]);
  useEffect(() => {
    const waiting = db.runs.filter(r => r.status === '生成中' || r.status === '更新中');
    if (!waiting.length) return;
    const t = setTimeout(() => setDb(v => ({
      ...v,
      runs: v.runs.map(r => {
        if (r.status === '更新中') return {
          ...r,
          status: '待复核',
          content: clone(r.draft),
          revision: r.revision + 1,
          reviewed: [],
          spent: r.spent + 2
        };
        if (r.status !== '生成中') return r;
        if (r.stage === 1 && r.scenario === '文案失败' && !r.recovered) return {
          ...r,
          status: '待处理',
          problem: '文案创作失败',
          recovered: true
        };
        if (r.stage === 2 && r.scenario === '结果未知' && !r.recovered) return {
          ...r,
          status: '待核查',
          unknownReservation: 8,
          problem: '画面生成结果未知',
          recovered: true
        };
        if (r.stage < 3) return {
          ...r,
          stage: r.stage + 1
        };
        const content = r.manualContent || demoContent(r.product);
        return {
          ...r,
          status: '待复核',
          stage: 4,
          content: clone(content),
          draft: clone(content),
          spent: 8
        };
      })
    })), 900);
    return () => clearTimeout(t);
  }, [db.runs]);
  function patchRun(p, id = run?.id) {
    setDb(v => ({
      ...v,
      runs: v.runs.map(r => r.id === id ? {
        ...r,
        ...p
      } : r)
    }));
  }
  function nav(p) {
    setPage(p);
    location.hash = p;
    setError('');
    window.scrollTo(0, 0);
  }
  function open(type, data = {}) {
    setError('');
    setModal({
      type,
      ...data
    });
  }
  function close() {
    setModal(null);
    setError('');
  }
  function pref(k, v) {
    setDb(d => ({
      ...d,
      prefs: {
        ...d.prefs,
        [k]: v
      }
    }));
  }
  function start(i = selected) {
    setSelected(i);
    setDb(v => ({
      ...v,
      current: null,
      prefs: {
        ...v.prefs,
        productCode: v.products[i].code
      }
    }));
    nav(2);
  }
  function view(r) {
    setDb(v => ({
      ...v,
      current: r.id
    }));
    nav(2);
  }
  function edit(p) {
    patchRun({
      draft: {
        ...run.draft,
        ...p
      },
      reviewed: [],
      status: '待复核'
    });
  }
  function saveText(k, value) {
    const arr = [...run.draft[k]];
    arr[platform] = value;
    edit({
      [k]: arr
    });
  }
  function err(msg) {
    setError(msg);
    return false;
  }
  function preflight() {
    if (!product?.confirmed) return err('请先核对商品事实并确认档案。');
    if (!db.prefs.platforms.some(Boolean)) return err('至少选择一个发布平台。');
    if (!Number.isInteger(+db.prefs.duration) || +db.prefs.duration <= 0) return err('视频时长请输入正整数秒数。');
    if (!Number.isFinite(+db.prefs.budget) || +db.prefs.budget < 8) return err('预算不足，请在高级设置中将预算调整至本次演示上界8元或以上。');
    open('generate');
  }
  function downloadPoster() {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([posterSvg(run, platform)], {
      type: 'image/svg+xml;charset=utf-8'
    }));
    a.download = run.product.name + '-' + ['抖音', '小红书'][platform] + '-海报示意图.svg';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    setToast('海报示意图已下载，非真实发布素材');
  }
  function download(review = false, mode = '完整套件') {
    const lines = ['营销工作台 · 视频与海报演示清单', review ? '已完成原型复核，非真实发布素材' : '内部样片 · 未审核', '导出范围：' + mode, '商品：' + run.product.name, '成片第' + run.revision + '版', '时长：' + run.duration + '秒'];
    run.platforms.forEach((on, i) => {
      if (on) {
        lines.push(['抖音', '小红书'][i], run.draft.title[i], run.draft.body[i]);
        if (mode !== '仅视频') lines.push('海报标题：' + run.content.posterTitle[i], '海报卖点：' + run.content.posterLine[i]);
        if (mode !== '仅海报') lines.push(...run.content.scripts[i]);
      }
    });
    lines.push('仅本机交互演示，不包含真实模型生成媒体。');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([lines.join('\n')], {
      type: 'text/plain;charset=utf-8'
    }));
    a.download = '营销作品演示清单.txt';
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    setToast('演示清单已下载');
  }
  function submit(e) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    if (modal.type === 'generate') {
      if (!f.get('consent')) return err('请确认资料处理范围与费用上界。');
      const r = {
        id: 'work-' + Date.now(),
        product: clone(product),
        platforms: clone(db.prefs.platforms),
        duration: +db.prefs.duration,
        brief: db.prefs.brief,
        budget: +db.prefs.budget,
        status: '生成中',
        stage: 0,
        revision: 1,
        reviewed: [],
        history: [],
        spent: 0,
        created: Date.now(),
        scenario
      };
      setDb(v => ({
        ...v,
        current: r.id,
        runs: [r, ...v.runs]
      }));
      close();
    } else if (modal.type === 'manual') {
      const c = demoContent(run.product);
      for (let i = 0; i < 2; i++) {
        if (!run.platforms[i]) continue;
        const values = ['title', 'body', 'shot0', 'shot1', 'shot2'].map(k => (f.get(k + i) || '').trim());
        if (values.some(v => !v)) return err('请补齐所选平台标题、发布文案和三镜口播。');
        c.title[i] = values[0];
        c.body[i] = values[1];
        c.scripts[i] = values.slice(2);
      }
      patchRun({
        manualContent: c,
        status: '生成中',
        stage: 1,
        origin: '人工创作'
      });
      close();
    } else if (modal.type === 'update') {
      if (!f.get('consent')) return err('请确认本次修改影响及费用。');
      if (run.spent + 2 > run.budget) return err('剩余预算不足，请先调整预算上限。');
      if (run.draft.scripts.some((a, i) => run.platforms[i] && a.some(t => !t.trim()))) return err('口播不能为空，请补齐或使用智能改写。');
      patchRun({
        status: '更新中',
        history: [{
          revision: run.revision,
          content: clone(run.content),
          draft: clone(run.draft)
        }, ...run.history],
        reviewed: []
      });
      close();
      setEditor('');
    } else if (modal.type === 'review') {
      const exportMode = modal.exportMode || '完整套件';
      if (exportMode === '仅海报' ? posterDirty : exportMode === '仅视频' ? videoDirty : dirty) return err('修改尚未应用，请先更新样片。');
      if (exportMode !== '仅海报' && run.badShots?.length) return err('存在已标记的问题画面，请替换后更新样片。');
      if (run.platforms.some((on, i) => on && (!run.draft.title[i].trim() || !run.draft.body[i].trim()))) return err('标题和发布文案不能为空。');
      if (!run.platforms.every((on, i) => !on || f.get('platform' + i))) return err('请逐个平台确认当前画面与营销文案。');
      if (!f.get('rights')) return err('请确认素材使用权、规格和标识。');
      patchRun({
        status: exportMode === '完整套件' ? '已复核' : '部分已复核',
        reviewed: run.platforms.map((on, i) => on ? i : null).filter(x => x !== null),
        content: {
          ...run.content,
          title: clone(run.draft.title),
          body: clone(run.draft.body)
        }
      });
      download(true, exportMode);
      close();
    } else if (modal.type === 'rewrite') {
      if (modal.phase !== 'candidate') {
        const scope = f.get('scope'),
          tone = f.get('tone');
        const base = scope === '发布文案' ? run.draft.body[platform] : run.draft.scripts[platform][0];
        setModal({
          ...modal,
          phase: 'candidate',
          scope,
          tone,
          original: base,
          candidate: tone === '更简洁' ? run.product.name + '，从真实细节开始了解。' : '一起看看' + run.product.name + '，为日常选择增加一点灵感。'
        });
        return;
      }
      patchRun({
        copyHistory: [{
          draft: clone(run.draft),
          revision: run.revision
        }, ...(run.copyHistory || [])]
      });
      const k = modal.scope === '发布文案' ? 'body' : 'scripts';
      if (k === 'body') {
        saveText('body', modal.candidate);
      } else {
        const scripts = clone(run.draft.scripts);
        scripts[platform][0] = modal.candidate;
        edit({
          scripts
        });
      }
      setToast('已采用候选，原版本保留');
      close();
    } else if (modal.type === 'product') {
      if (!f.get('facts')) return err('请核对商品事实与来源。');
      const p = db.products[modal.index];
      if (!p.files.some(n => /正面图|\.(png|jpe?g)$/i.test(n))) return err('请补充商品图片后确认。');
      setDb(v => ({
        ...v,
        products: v.products.map((x, i) => i === modal.index ? {
          ...x,
          confirmed: true
        } : x)
      }));
      setSelected(modal.index);
      close();
      start(modal.index);
    } else if (modal.type === 'new') {
      if (!f.get('name')?.trim() || !f.get('code')?.trim() || !f.get('spec')?.trim()) return err('请填写商品名称、编号及规格。');
      if (db.products.some(p => p.code === f.get('code'))) return err('商品编号已存在。');
      if (!modal.files?.length) return err('请添加商品图片。');
      if (!f.get('rights')) return err('请确认素材使用权。');
      setDb(v => ({
        ...v,
        products: [...v.products, {
          name: f.get('name'),
          code: f.get('code'),
          spec: f.get('spec'),
          files: modal.files,
          type: f.get('type') === '吹风机' ? 1 : 0,
          confirmed: false,
          version: 1
        }]
      }));
      close();
      nav(1);
    } else if (modal.type === 'cancel') {
      patchRun({
        status: '已取消'
      });
      close();
      setToast('已停止后续步骤，已有记录保留');
    } else if (modal.type === 'budget') {
      const value = +f.get('budget');
      if (!Number.isFinite(value) || value < run.spent) return err('预算不能低于已发生演示费用。');
      patchRun({
        budget: value
      });
      close();
    } else close();
  }
  const card = (p, i) => React.createElement("article", {
    className: "card",
    key: p.code
  }, React.createElement(Art, {
    type: p.type,
    scene: i % 3
  }), React.createElement("div", {
    className: "cardbody"
  }, React.createElement("div", {
    className: "row"
  }, React.createElement("h2", null, p.name), React.createElement(Tag, {
    warn: !p.confirmed
  }, p.confirmed ? '已确认' : '待确认')), React.createElement("div", {
    className: "specrow"
  }, p.spec, React.createElement("span", null, p.files.length, " \u4EFD\u8D44\u6599")), React.createElement("div", {
    className: "cardfooter"
  }, React.createElement("button", {
    onClick: () => open('product', {
      index: i
    })
  }, "\u67E5\u770B\u6863\u6848"), React.createElement("button", {
    className: p.confirmed ? 'primary' : '',
    onClick: () => p.confirmed ? start(i) : open('product', {
      index: i
    })
  }, p.confirmed ? '用此商品创作' : '确认商品事实'))));
  const workCard = r => React.createElement("article", {
    className: "card",
    key: r.id
  }, React.createElement(Art, {
    type: r.product.type
  }), React.createElement("div", {
    className: "cardbody"
  }, React.createElement("div", {
    className: "row"
  }, React.createElement("h2", null, r.product.name), React.createElement(Tag, {
    warn: r.status !== '已复核'
  }, r.status)), React.createElement("div", {
    className: "specrow"
  }, r.platforms.map((on, i) => on ? ['抖音', '小红书'][i] : '').filter(Boolean).join('、'), React.createElement("span", null, r.duration, " \u79D2 \xB7 \u7B2C ", r.revision, " \u7248")), React.createElement("div", {
    className: "cardfooter"
  }, React.createElement("span", null, new Date(r.created).toLocaleDateString('zh-CN')), React.createElement("button", {
    onClick: () => view(r)
  }, r.content ? '打开作品' : '查看进度'))));
  const home = React.createElement(React.Fragment, null, React.createElement("div", {
    className: "launchgrid"
  }, React.createElement("section", {
    className: "hero"
  }, React.createElement("h2", null, "\u9009\u597D\u5546\u54C1", React.createElement("br", null), "\u89C6\u9891\u6D77\u62A5\u4E00\u8D77\u521B\u4F5C"), React.createElement("button", {
    className: "dark",
    onClick: () => start()
  }, "\u5F00\u59CB\u4E00\u952E\u751F\u6210"), React.createElement("div", {
    className: "hero-art"
  }, React.createElement(Art, null))), React.createElement("section", {
    className: "panel journey"
  }, React.createElement("h2", null, "\u4E09\u6B65\u5B8C\u6210\u8425\u9500\u521B\u4F5C"), [['选择商品', '商品事实一次确认，后续创作直接复用'], ['一键生成', '文案、视频与配套海报自动完成'], ['复核导出', '满意即可导出，需要时再修改']].map(([n, t], i) => React.createElement("div", {
    className: "journey-row",
    key: n
  }, React.createElement("span", null, i + 1), React.createElement("b", null, n), React.createElement("div", null, t))))), React.createElement("section", {
    className: "section"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, "\u6700\u8FD1\u4F5C\u54C1"), React.createElement("button", {
    onClick: () => nav(3)
  }, "\u5168\u90E8\u4F5C\u54C1")), db.runs.length ? React.createElement("div", {
    className: "grid"
  }, db.runs.slice(0, 3).map(workCard)) : React.createElement("div", {
    className: "panel empty"
  }, React.createElement("h2", null, "\u4ECE\u7B2C\u4E00\u4EF6\u5546\u54C1\u5F00\u59CB"), React.createElement("button", {
    onClick: () => start()
  }, "\u4E00\u952E\u751F\u6210"))), React.createElement("section", {
    className: "section"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, "\u53EF\u7528\u5546\u54C1"), React.createElement("button", {
    onClick: () => nav(1)
  }, "\u7BA1\u7406\u5546\u54C1")), React.createElement("div", {
    className: "grid"
  }, db.products.slice(0, 3).map(card))));
  const catalog = React.createElement(React.Fragment, null, React.createElement("div", {
    className: "bar"
  }, React.createElement("div", {
    className: "tabs"
  }, ['全部', '已确认', '待确认'].map(x => React.createElement("button", {
    key: x,
    className: filter === x ? 'selected' : '',
    onClick: () => setFilter(x)
  }, x))), React.createElement("input", {
    "aria-label": "\u641C\u7D22\u5546\u54C1\u540D\u79F0",
    placeholder: "\u641C\u7D22\u5546\u54C1\u540D\u79F0",
    value: query,
    onChange: e => setQuery(e.target.value)
  })), React.createElement("div", {
    className: "grid"
  }, db.products.map((p, i) => ({
    p,
    i
  })).filter(({
    p
  }) => p.name.includes(query) && (filter === '全部' || p.confirmed === (filter === '已确认'))).map(({
    p,
    i
  }) => card(p, i))), !db.products.some(p => p.name.includes(query)) && React.createElement("div", {
    className: "empty"
  }, "\u6CA1\u6709\u5339\u914D\u5546\u54C1", React.createElement("button", {
    onClick: () => setQuery('')
  }, "\u6E05\u7A7A\u641C\u7D22")));
  function posterView(content, i, small = false) {
    return React.createElement("div", {
      className: 'marketing-poster poster-platform-' + i + (small ? ' poster-small' : '')
    }, React.createElement("div", {
      className: "poster-top"
    }, React.createElement("span", null, "\u65E5\u5E38\u597D\u7269"), React.createElement("span", null, run.product.name)), React.createElement("h2", null, content.posterTitle?.[i] || run.product.name), React.createElement("p", null, content.posterLine?.[i] || '从商品细节开始了解'), React.createElement(Art, {
      type: run.product.type,
      scene: content.posterScene?.[i] || 0
    }), React.createElement("div", {
      className: "poster-bottom"
    }, React.createElement("b", null, "\u53D1\u73B0\u65E5\u5E38\u65B0\u7075\u611F"), React.createElement("span", null, run.product.spec)), React.createElement("span", {
      className: "poster-demo"
    }, "\u6D77\u62A5\u8BBE\u8BA1\u793A\u610F"));
  }
  const steps = React.createElement("div", {
    className: "flow-steps",
    "aria-label": "\u521B\u4F5C\u6D41\u7A0B"
  }, ['选择商品', '一键生成', '复核导出'].map((n, i) => React.createElement("div", {
    key: n,
    className: i === (!run ? 0 : run.content ? 2 : 1) ? 'current' : ''
  }, React.createElement("span", null, i + 1), n)));
  const setup = React.createElement(React.Fragment, null, React.createElement("div", {
    className: "quick-create"
  }, React.createElement("section", {
    className: "panel"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, "\u9009\u62E9\u5546\u54C1"), React.createElement("button", {
    onClick: () => open('choose')
  }, "\u66F4\u6362\u5546\u54C1")), React.createElement("div", {
    className: "one-product"
  }, React.createElement(Art, {
    type: product.type
  }), React.createElement("div", null, React.createElement("h2", null, product.name), React.createElement("div", {
    className: "lineitem"
  }, product.spec, React.createElement(Tag, {
    warn: !product.confirmed
  }, product.confirmed ? '事实已确认' : '待确认')), React.createElement("button", {
    onClick: () => open('product', {
      index: selected
    })
  }, "\u67E5\u770B\u4E8B\u5B9E\u6765\u6E90"))), React.createElement("div", {
    className: "two"
  }, React.createElement("div", {
    className: "field"
  }, "\u53D1\u5E03\u5E73\u53F0", React.createElement("div", {
    className: "platform-picker"
  }, ['抖音', '小红书'].map((n, i) => React.createElement("label", {
    className: "choice",
    key: n
  }, React.createElement("input", {
    type: "checkbox",
    checked: db.prefs.platforms[i],
    onChange: e => pref('platforms', db.prefs.platforms.map((v, j) => i === j ? e.target.checked : v))
  }), n)))), React.createElement(Field, {
    label: "\u89C6\u9891\u65F6\u957F\uFF08\u79D2\uFF09"
  }, React.createElement("input", {
    type: "number",
    min: "1",
    step: "1",
    value: db.prefs.duration,
    onChange: e => pref('duration', e.target.value)
  }))), React.createElement("details", null, React.createElement("summary", null, "\u9AD8\u7EA7\u8BBE\u7F6E"), React.createElement(Field, {
    label: "\u521B\u610F\u8981\u6C42\uFF08\u9009\u586B\uFF09"
  }, React.createElement("textarea", {
    value: db.prefs.brief,
    onChange: e => pref('brief', e.target.value),
    placeholder: "\u7559\u7A7A\u5373\u53EF\u6839\u636E\u5546\u54C1\u8D44\u6599\u81EA\u52A8\u521B\u4F5C"
  })), React.createElement(Field, {
    label: "\u9884\u7B97\u4E0A\u9650\uFF08\u5143\uFF09"
  }, React.createElement("input", {
    type: "number",
    value: db.prefs.budget,
    onChange: e => pref('budget', e.target.value)
  })), React.createElement("div", {
    className: "lineitem"
  }, "\u53D7\u4F17\u3001\u8BED\u6C14\u3001\u914D\u97F3\u4E0E\u914D\u4E50", React.createElement(Tag, null, "\u81EA\u52A8\u5339\u914D"))), error && React.createElement("div", {
    role: "alert",
    className: "error"
  }, error), React.createElement("div", {
    className: "bottom"
  }, React.createElement(Tag, null, "\u8425\u9500\u6587\u6848\u81EA\u52A8\u521B\u4F5C"), React.createElement("button", {
    className: "primary",
    onClick: preflight
  }, "\u4E00\u952E\u751F\u6210"))), React.createElement("section", {
    className: "panel"
  }, React.createElement("h2", null, "\u672C\u6B21\u4F5C\u54C1"), [['营销视频', db.prefs.platforms.filter(Boolean).length + ' 条'], ['营销海报', db.prefs.platforms.filter(Boolean).length + ' 张'], ['标题与发布文案', '按平台生成'], ['商品图与视频封面', '自动配套'], ['配音、字幕、配乐', '自动匹配']].map(([n, v]) => React.createElement("div", {
    className: "lineitem",
    key: n
  }, n, React.createElement("b", null, v))), React.createElement("div", {
    className: "automation-mark"
  }, React.createElement(NavIcon, {
    n: 5
  }), React.createElement("b", null, "\u89C6\u9891\u4E0E\u6D77\u62A5\uFF0C\u4E00\u6B21\u751F\u6210")))), React.createElement("details", {
    className: "scenario"
  }, React.createElement("summary", null, "\u6F14\u793A\u573A\u666F"), React.createElement(Field, {
    label: "\u751F\u6210\u573A\u666F"
  }, React.createElement("select", {
    value: scenario,
    onChange: e => setScenario(e.target.value)
  }, ['正常生成', '文案失败', '结果未知'].map(n => React.createElement("option", {
    key: n
  }, n)))), React.createElement("span", null, "\u4EC5\u6F14\u793A\u72B6\u6001\u5207\u6362\uFF0C\u4E0D\u8C03\u7528\u5916\u90E8\u670D\u52A1\u3002")));
  const progress = run && React.createElement("section", {
    className: "panel generation"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, run.status === '生成中' ? '正在制作作品' : run.status === '更新中' ? '正在应用修改' : run.status === '已暂停' ? '制作已暂停' : run.status === '已取消' ? '制作已取消' : '需要处理'), React.createElement(Tag, null, run.product.name)), React.createElement("div", {
    className: "generation-steps"
  }, FLOW_STAGES.map((n, i) => React.createElement("div", {
    className: run.stage === i ? 'current' : '',
    key: n
  }, React.createElement("span", null, run.status === '更新中' ? i === 3 ? '重新合成' : '按修改范围复用' : i < run.stage ? '已完成' : run.stage === i ? run.status : '待执行'), React.createElement("b", null, n)))), ['待处理', '待核查'].includes(run.status) && React.createElement("div", {
    className: "notice"
  }, React.createElement("b", null, run.problem), React.createElement("p", null, run.status === '待核查' ? '保留当前请求和费用预留，核查前不会重新提交。' : '已完成内容保留，仅恢复失败阶段。')), React.createElement("div", {
    className: "bottom"
  }, React.createElement("button", {
    onClick: () => nav(4)
  }, "\u67E5\u770B\u4EFB\u52A1"), run.status === '生成中' && React.createElement("button", {
    onClick: () => patchRun({
      status: '已暂停'
    })
  }, "\u6682\u505C\u5236\u4F5C"), run.status === '已暂停' && React.createElement("button", {
    className: "primary",
    onClick: () => patchRun({
      status: '生成中'
    })
  }, "\u7EE7\u7EED\u5236\u4F5C"), run.status === '待处理' && React.createElement(React.Fragment, null, React.createElement("button", {
    className: "primary",
    onClick: () => patchRun({
      status: '生成中'
    })
  }, "\u6062\u590D\u5931\u8D25\u9636\u6BB5"), React.createElement("button", {
    onClick: () => open('manual')
  }, "\u624B\u5DE5\u63A5\u7BA1")), run.status === '待核查' && React.createElement("button", {
    onClick: () => open('unknown')
  }, "\u6838\u67E5\u72B6\u6001"), ['生成中', '已暂停', '待处理', '待核查'].includes(run.status) && React.createElement("button", {
    onClick: () => open('cancel')
  }, "\u53D6\u6D88\u540E\u7EED\u6B65\u9AA4"), run.status === '已取消' && React.createElement("button", {
    onClick: () => start()
  }, "\u65B0\u5EFA\u521B\u4F5C")));
  const currentShot = run?.content ? Math.min(2, Math.floor(time / (run.duration / 3))) : 0;
  const result = run?.content && React.createElement(React.Fragment, null, React.createElement("div", {
    className: "output-tabs"
  }, ['视频', '海报'].map(n => React.createElement("button", {
    key: n,
    className: mediaMode === n ? 'selected' : '',
    onClick: () => {
      setMediaMode(n);
      setEditor('');
      setPlaying(false);
    }
  }, n))), React.createElement("div", {
    className: "bar"
  }, React.createElement("div", {
    className: "tabs"
  }, run.platforms.map((on, i) => on && React.createElement("button", {
    key: i,
    className: platform === i ? 'selected' : '',
    onClick: () => {
      setPlatform(i);
      setTime(0);
    }
  }, ['抖音', '小红书'][i]))), React.createElement("div", {
    className: "tabs"
  }, React.createElement(Tag, {
    warn: run.status !== '已复核'
  }, run.status, " \xB7 \u7B2C ", run.revision, " \u7248"), React.createElement("button", {
    onClick: () => open('versions')
  }, "\u5386\u53F2\u7248\u672C"), React.createElement("button", {
    onClick: () => start()
  }, "\u65B0\u5EFA\u521B\u4F5C"))), React.createElement("div", {
    className: "result-grid"
  }, React.createElement("section", {
    className: "panel"
  }, mediaMode === '视频' ? React.createElement(React.Fragment, null, React.createElement("div", {
    className: 'player ' + (playing ? 'playing' : '')
  }, React.createElement("div", {
    className: "film"
  }, React.createElement("span", {
    className: "sample-label"
  }, "\u4EA4\u4E92\u6837\u7247 \xB7 \u7B2C ", run.revision, " \u7248"), React.createElement(Art, {
    type: run.product.type,
    scene: run.content.images[currentShot]
  }), React.createElement("div", {
    className: 'caption ' + (run.content.subtitle === '黑字浅底' ? 'light' : '')
  }, run.content.scripts[platform][currentShot]))), React.createElement("div", {
    className: "playbar"
  }, React.createElement("button", {
    onClick: () => setPlaying(!playing)
  }, playing ? '暂停' : '播放'), React.createElement("input", {
    "aria-label": "\u64AD\u653E\u8FDB\u5EA6",
    type: "range",
    min: "0",
    max: run.duration,
    value: time,
    onChange: e => setTime(+e.target.value)
  }), React.createElement("span", null, time, " / ", run.duration, " \u79D2"))) : React.createElement("div", {
    className: "poster-stage"
  }, posterView(run.content, platform)), React.createElement("div", {
    className: "edit-actions"
  }, (mediaMode === '海报' ? [['poster', '修改海报']] : [['copy', '改文案'], ['image', '换画面'], ['sound', '换声音']]).map(([id, n]) => React.createElement("button", {
    key: id,
    className: editor === id ? 'selected' : '',
    "aria-expanded": editor === id,
    onClick: () => setEditor(editor === id ? '' : id)
  }, n)))), React.createElement("section", {
    className: "panel result-copy"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, mediaMode === '海报' ? '海报与发布文案' : '营销文案'), React.createElement(Tag, null, run.origin || '智能创作演示')), React.createElement(Field, {
    label: "\u53D1\u5E03\u6807\u9898"
  }, React.createElement("input", {
    value: run.draft.title[platform],
    onChange: e => saveText('title', e.target.value)
  })), React.createElement(Field, {
    label: "\u53D1\u5E03\u6587\u6848"
  }, React.createElement("textarea", {
    value: run.draft.body[platform],
    onChange: e => saveText('body', e.target.value)
  })), React.createElement("button", {
    onClick: () => open('rewrite', {
      phase: 'request'
    })
  }, "\u667A\u80FD\u6539\u5199"), React.createElement("div", {
    className: "lineitem"
  }, "\u5546\u54C1\u4E8B\u5B9E\u6765\u6E90", React.createElement("button", {
    onClick: () => open('facts')
  }, "\u67E5\u770B")), dirty ? React.createElement("div", {
    className: "notice"
  }, React.createElement("b", null, "\u6709\u4FEE\u6539\u5C1A\u672A\u5E94\u7528"), React.createElement("p", null, "\u9884\u89C8\u4FDD\u7559\u7B2C ", run.revision, " \u7248\uFF0C\u66F4\u65B0\u540E\u518D\u590D\u6838\u3002"), React.createElement("button", {
    className: "primary",
    onClick: () => open('update')
  }, "\u66F4\u65B0\u6837\u7247"), React.createElement("button", {
    onClick: () => {
      patchRun({
        draft: {
          ...clone(run.content),
          title: clone(run.draft.title),
          body: clone(run.draft.body)
        }
      });
      setEditor('');
    }
  }, "\u64A4\u9500\u672A\u5E94\u7528\u4FEE\u6539")) : React.createElement("button", {
    className: "primary full",
    onClick: () => open('review')
  }, "\u590D\u6838\u5E76\u5BFC\u51FA"), mediaMode === '海报' && React.createElement("button", {
    className: "full",
    onClick: downloadPoster
  }, "\u4E0B\u8F7D\u6D77\u62A5\u793A\u610F\u56FE"), React.createElement("button", {
    className: "full",
    onClick: () => download()
  }, "\u4E0B\u8F7D\u89C6\u9891\u4E0E\u6D77\u62A5\u6E05\u5355"))), editor && React.createElement("section", {
    className: "panel section edit-panel"
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", null, editor === 'poster' ? '海报编辑' : editor === 'copy' ? '文案与分镜' : editor === 'image' ? '画面调整' : '声音与字幕'), React.createElement("button", {
    onClick: () => setEditor('')
  }, "\u6536\u8D77\u7F16\u8F91")), editor === 'poster' ? React.createElement("div", {
    className: "three"
  }, React.createElement(Field, {
    label: "\u6D77\u62A5\u6807\u9898"
  }, React.createElement("input", {
    maxLength: "24",
    value: run.draft.posterTitle[platform],
    onChange: e => saveText('posterTitle', e.target.value)
  })), React.createElement(Field, {
    label: "\u6D77\u62A5\u5356\u70B9\u6587\u6848"
  }, React.createElement("textarea", {
    maxLength: "32",
    value: run.draft.posterLine[platform],
    onChange: e => saveText('posterLine', e.target.value)
  })), React.createElement(Field, {
    label: "\u6D77\u62A5\u753B\u9762"
  }, React.createElement("select", {
    value: run.draft.posterScene[platform],
    onChange: e => {
      const a = [...run.draft.posterScene];
      a[platform] = +e.target.value;
      edit({
        posterScene: a
      });
    }
  }, React.createElement("option", {
    value: "0"
  }, "\u6E05\u723D\u80CC\u666F"), React.createElement("option", {
    value: "1"
  }, "\u6696\u8272\u684C\u9762"), React.createElement("option", {
    value: "2"
  }, "\u6D45\u84DD\u7A7A\u95F4")))) : editor === 'copy' ? React.createElement(React.Fragment, null, React.createElement("div", {
    className: "three"
  }, run.draft.scripts[platform].map((t, i) => React.createElement("div", {
    key: i
  }, React.createElement("div", {
    className: "lineitem"
  }, "\u7B2C ", i + 1, " \u955C", React.createElement("span", null, (i * run.duration / 3).toFixed(1), "\u2014", ((i + 1) * run.duration / 3).toFixed(1), " \u79D2")), React.createElement(Field, {
    label: '第 ' + (i + 1) + ' 镜口播'
  }, React.createElement("textarea", {
    value: t,
    onChange: e => {
      const scripts = clone(run.draft.scripts);
      scripts[platform][i] = e.target.value;
      edit({
        scripts
      });
    }
  }))))), React.createElement("button", {
    onClick: () => open('rewrite', {
      phase: 'request'
    })
  }, "\u667A\u80FD\u6539\u5199")) : editor === 'image' ? React.createElement("div", {
    className: "three"
  }, run.draft.images.map((n, i) => React.createElement("div", {
    key: i
  }, React.createElement("h3", null, "\u7B2C ", i + 1, " \u955C"), React.createElement(Art, {
    type: run.product.type,
    scene: n
  }), React.createElement(Field, {
    label: '第 ' + (i + 1) + ' 镜画面'
  }, React.createElement("select", {
    value: n,
    onChange: e => {
      edit({
        images: run.draft.images.map((x, j) => i === j ? +e.target.value : x)
      });
      patchRun({
        badShots: (run.badShots || []).filter(n => n !== i)
      });
    }
  }, React.createElement("option", {
    value: "0"
  }, "\u539F\u56FE \xB7 \u6E05\u723D\u80CC\u666F"), React.createElement("option", {
    value: "1"
  }, "\u573A\u666F \xB7 \u6696\u8272\u684C\u9762"), React.createElement("option", {
    value: "2"
  }, "\u573A\u666F \xB7 \u6D45\u84DD\u7A7A\u95F4"))), React.createElement("button", {
    onClick: () => {
      patchRun({
        badShots: [...new Set([...(run.badShots || []), i])],
        reviewed: [],
        status: '待复核'
      });
      setToast('画面已标记，请选择其他画面并更新样片');
    }
  }, run.badShots?.includes(i) ? '存在问题，待替换' : '标记画面有问题')))) : React.createElement("div", {
    className: "three"
  }, [['配音', 'voice', ['自然女声', '沉稳男声', '清新女声']], ['配乐', 'music', ['轻快日常', '舒缓轻音乐', '不使用配乐']], ['字幕样式', 'subtitle', ['白字深底', '黑字浅底']]].map(([n, k, opts]) => React.createElement(Field, {
    key: k,
    label: n
  }, React.createElement("select", {
    value: run.draft[k],
    onChange: e => edit({
      [k]: e.target.value
    })
  }, opts.map(x => React.createElement("option", {
    key: x
  }, x)))))), React.createElement("div", {
    className: "bottom"
  }, React.createElement("span", {
    className: "muted"
  }, "\u4FEE\u6539\u81EA\u52A8\u4FDD\u5B58\u4E3A\u8349\u7A3F"), React.createElement("button", {
    className: "primary",
    disabled: !dirty,
    onClick: () => open('update')
  }, "\u5E94\u7528\u4FEE\u6539\u5E76\u66F4\u65B0\u4F5C\u54C1"))));
  const workspace = React.createElement(React.Fragment, null, steps, !run ? setup : !run.content || run.status === '更新中' ? progress : result);
  const works = React.createElement(React.Fragment, null, db.runs.length ? React.createElement("div", {
    className: "grid"
  }, db.runs.map(workCard)) : React.createElement("div", {
    className: "panel empty"
  }, React.createElement("h2", null, "\u8FD8\u6CA1\u6709\u4F5C\u54C1"), React.createElement("button", {
    className: "primary",
    onClick: () => start()
  }, "\u5F00\u59CB\u4E00\u952E\u751F\u6210")));
  const tasks = React.createElement("section", {
    className: "panel"
  }, React.createElement("h2", null, "\u5236\u4F5C\u4EFB\u52A1"), db.runs.length ? React.createElement("table", null, React.createElement("thead", null, React.createElement("tr", null, React.createElement("th", null, "\u5546\u54C1"), React.createElement("th", null, "\u4EFB\u52A1\u72B6\u6001"), React.createElement("th", null, "\u5F53\u524D\u9636\u6BB5"), React.createElement("th", null, "\u6F14\u793A\u8D39\u7528"), React.createElement("th", null, "\u64CD\u4F5C"))), React.createElement("tbody", null, db.runs.map(r => React.createElement("tr", {
    key: r.id
  }, React.createElement("td", null, r.product.name), React.createElement("td", null, React.createElement(Tag, {
    warn: active.includes(r.status)
  }, r.status)), React.createElement("td", null, r.content ? '样片第 ' + r.revision + ' 版' : FLOW_STAGES[Math.min(r.stage, 3)]), React.createElement("td", null, r.unknownReservation ? '未知预留 ¥8.00' : '已发生 ¥' + r.spent.toFixed(2)), React.createElement("td", null, React.createElement("button", {
    onClick: () => view(r)
  }, "\u6253\u5F00\u4EFB\u52A1")))))) : React.createElement("div", {
    className: "empty"
  }, "\u6682\u65E0\u5236\u4F5C\u4EFB\u52A1"), React.createElement("div", {
    className: "notice"
  }, "\u672C\u673A\u6F14\u793A\u4E0D\u4EA7\u751F\u5B9E\u9645\u8D39\u7528\u3002\u771F\u5B9E\u4EFB\u52A1\u7ED3\u679C\u672A\u77E5\u65F6\u4FDD\u7559\u8D39\u7528\u9884\u7559\uFF0C\u6838\u67E5\u540E\u5904\u7406\u3002"));
  const modalTitles = {
    manual: '手工接管文案',
    generate: '确认本次生成',
    review: '复核当前作品',
    rewrite: '智能改写',
    update: '应用修改',
    choose: '选择商品',
    product: '商品资料',
    new: '新建商品',
    cancel: '取消后续步骤',
    unknown: '核查外部结果',
    facts: '商品事实来源',
    versions: '历史版本',
    budget: '调整预算'
  };
  return React.createElement(React.Fragment, null, React.createElement("a", {
    className: "skip",
    href: "#content"
  }, "\u8DF3\u81F3\u4E3B\u8981\u5185\u5BB9"), React.createElement("aside", null, React.createElement("div", {
    className: "brand"
  }, React.createElement("span", {
    className: "brandmark"
  }, React.createElement(NavIcon, {
    n: 0
  })), "\u6620\u7269"), React.createElement("nav", {
    "aria-label": "\u4E3B\u5BFC\u822A"
  }, FLOW_NAMES.map((n, i) => React.createElement("button", {
    key: n,
    className: page === i ? 'active' : '',
    "aria-current": page === i ? 'page' : undefined,
    onClick: () => nav(i)
  }, React.createElement(FlowNavIcon, {
    n: i
  }), n))), React.createElement("div", {
    className: "sidebar-note"
  }, React.createElement("span", {
    className: "status-dot"
  }), "\u672C\u673A\u4EA4\u4E92\u6F14\u793A"), React.createElement("div", {
    className: "sidebottom"
  }, React.createElement("span", {
    className: "avatar"
  }, "\u6797"), React.createElement("b", null, "\u6797\u6653"), React.createElement("span", {
    className: "muted"
  }, "\u5546\u5BB6\u8D26\u53F7"))), React.createElement("main", null, React.createElement("div", {
    id: "content",
    "data-screen-label": FLOW_NAMES[page]
  }, React.createElement("div", {
    className: "title"
  }, React.createElement("h1", null, page === 2 && run?.content ? '作品详情' : FLOW_NAMES[page]), page === 1 ? React.createElement("button", {
    className: "primary",
    onClick: () => open('new')
  }, "\u65B0\u5EFA\u5546\u54C1") : page !== 2 ? React.createElement("button", {
    className: "primary",
    onClick: () => start()
  }, "\u65B0\u5EFA\u521B\u4F5C") : run && React.createElement(Tag, null, run.product.name)), [home, catalog, workspace, works, tasks][page])), React.createElement("dialog", {
    ref: dialog,
    "aria-labelledby": "dialog-title",
    onCancel: close
  }, React.createElement("form", {
    onSubmit: submit
  }, React.createElement("div", {
    className: "bar"
  }, React.createElement("h2", {
    id: "dialog-title"
  }, modalTitles[modal?.type]), React.createElement("button", {
    type: "button",
    "aria-label": "\u5173\u95ED\u5F39\u7A97",
    onClick: close
  }, "\xD7")), error && React.createElement("div", {
    className: "error",
    role: "alert"
  }, error), modal?.type === 'manual' && React.createElement(React.Fragment, null, run.platforms.map((on, i) => on && React.createElement("section", {
    className: "review-platform",
    key: i
  }, React.createElement("h3", null, ['抖音', '小红书'][i]), React.createElement(Field, {
    label: ['抖音', '小红书'][i] + '标题'
  }, React.createElement("input", {
    name: 'title' + i
  })), React.createElement(Field, {
    label: ['抖音', '小红书'][i] + '发布文案'
  }, React.createElement("textarea", {
    name: 'body' + i
  })), [0, 1, 2].map(j => React.createElement(Field, {
    key: j,
    label: ['抖音', '小红书'][i] + '第' + (j + 1) + '镜口播'
  }, React.createElement("input", {
    name: 'shot' + j + i
  })))))), modal?.type === 'generate' && React.createElement(React.Fragment, null, React.createElement("table", null, React.createElement("tbody", null, [['商品', product.name], ['平台', ['抖音', '小红书'].filter((_, i) => db.prefs.platforms[i]).join('、')], ['时长', db.prefs.duration + ' 秒'], ['处理内容', '营销文案、分镜、画面、配音、字幕、视频合成与海报排版'], ['资料与用途', '当前已确认商品资料，仅用于本次创作'], ['服务商', '本地演示，未接入真实服务'], ['费用上界', '¥8.00（本次全部阶段演示值）']].map(([n, v]) => React.createElement("tr", {
    key: n
  }, React.createElement("th", null, n), React.createElement("td", null, v))))), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: "consent"
  }), "\u786E\u8BA4\u8D44\u6599\u5904\u7406\u8303\u56F4\u4E0E\u8D39\u7528\u4E0A\u754C")), modal?.type === 'choose' && React.createElement("div", {
    className: "choose-list"
  }, db.products.map((p, i) => React.createElement("button", {
    type: "button",
    key: p.code,
    onClick: () => {
      setSelected(i);
      pref('productCode', db.products[i].code);
      close();
    }
  }, React.createElement("span", null, p.name, " \xB7 ", p.spec), React.createElement(Tag, {
    warn: !p.confirmed
  }, p.confirmed ? '已确认' : '待确认')))), modal?.type === 'review' && React.createElement(React.Fragment, null, React.createElement(Field, {
    label: "\u5BFC\u51FA\u5185\u5BB9"
  }, React.createElement("select", {
    value: modal.exportMode || '完整套件',
    onChange: e => setModal({
      ...modal,
      exportMode: e.target.value
    })
  }, React.createElement("option", null, "\u5B8C\u6574\u5957\u4EF6"), React.createElement("option", null, "\u4EC5\u89C6\u9891"), React.createElement("option", null, "\u4EC5\u6D77\u62A5"))), modal.exportMode !== '仅海报' && React.createElement("div", {
    className: "three review-images"
  }, run.content.images.map((n, i) => React.createElement("div", {
    key: i
  }, React.createElement("h3", null, "\u7B2C ", i + 1, " \u955C"), React.createElement(Art, {
    type: run.product.type,
    scene: n
  })))), run.platforms.map((on, i) => on && React.createElement("section", {
    className: "review-platform",
    key: i
  }, React.createElement("h3", null, ['抖音', '小红书'][i]), modal.exportMode !== '仅视频' && React.createElement("div", {
    className: "review-poster"
  }, posterView(run.content, i, true)), React.createElement("b", null, run.draft.title[i]), React.createElement("p", null, run.draft.body[i]), modal.exportMode !== '仅海报' && React.createElement("p", null, run.content.scripts[i].join(' / ')), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: 'platform' + i
  }), "\u5DF2\u6838\u5BF9", ['抖音', '小红书'][i], "\u7684", modal.exportMode === '仅海报' ? '海报' : modal.exportMode === '仅视频' ? '视频' : '视频与海报', "\u3001\u5546\u54C1\u4E8B\u5B9E\u4E0E\u8425\u9500\u8868\u8FBE"))), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: "rights"
  }), "\u5DF2\u6838\u5BF9\u7D20\u6750\u4F7F\u7528\u6743\u3001\u89C4\u683C\u548C\u6807\u8BC6"), React.createElement("div", {
    className: "notice"
  }, "\u5F53\u524D\u4EC5\u4E0B\u8F7D\u6F14\u793A\u6E05\u5355\uFF0C\u4E0D\u542B\u771F\u5B9E\u5A92\u4F53\u6216\u5E73\u53F0\u53D1\u5E03\u8BB8\u53EF\u3002")), modal?.type === 'update' && React.createElement(React.Fragment, null, React.createElement("table", null, React.createElement("tbody", null, React.createElement("tr", null, React.createElement("th", null, "\u4FEE\u6539\u8303\u56F4"), React.createElement("td", null, ['scripts', 'images', 'voice', 'music', 'subtitle', 'posterTitle', 'posterLine', 'posterScene'].filter(k => JSON.stringify(run.draft[k]) !== JSON.stringify(run.content[k])).map(k => ({
    scripts: '口播',
    images: '画面引用',
    voice: '配音',
    music: '配乐',
    subtitle: '字幕',
    posterTitle: '海报标题',
    posterLine: '海报卖点',
    posterScene: '海报画面'
  })[k]).join('、'))), React.createElement("tr", null, React.createElement("th", null, "\u6267\u884C\u5F71\u54CD"), React.createElement("td", null, posterDirty && !videoDirty ? '仅重排所选平台海报，视频、配音和其他海报全部复用' : videoDirty && !posterDirty ? '仅更新受影响视频，已生成海报全部复用' : '分别更新受影响视频和海报，复用其余素材')), React.createElement("tr", null, React.createElement("th", null, "\u7248\u672C"), React.createElement("td", null, "\u5EFA\u7ACB\u7B2C ", run.revision + 1, " \u7248\uFF0C\u4FDD\u7559\u7B2C ", run.revision, " \u7248")), React.createElement("tr", null, React.createElement("th", null, "\u8D39\u7528\u4E0A\u754C"), React.createElement("td", null, "\xA52.00\uFF08\u6F14\u793A\uFF09")))), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: "consent"
  }), "\u786E\u8BA4\u4FEE\u6539\u5F71\u54CD\u4E0E\u8D39\u7528"), React.createElement("button", {
    type: "button",
    onClick: () => open('budget')
  }, "\u8C03\u6574\u9884\u7B97\u4E0A\u9650")), modal?.type === 'rewrite' && (modal.phase === 'candidate' ? React.createElement(React.Fragment, null, React.createElement("div", {
    className: "notice"
  }, "\u672C\u5730\u6F14\u793A\u5019\u9009\uFF0C\u672A\u8C03\u7528\u6A21\u578B\uFF1B\u91C7\u7528\u540E\u624D\u4FEE\u6539\u8349\u7A3F\u3002"), React.createElement("h3", null, "\u539F\u6587"), React.createElement("p", null, modal.original), React.createElement("h3", null, "\u65B0\u5019\u9009"), React.createElement("p", null, modal.candidate)) : React.createElement(React.Fragment, null, React.createElement(Field, {
    label: "\u4FEE\u6539\u5185\u5BB9"
  }, React.createElement("select", {
    name: "scope"
  }, React.createElement("option", null, "\u53D1\u5E03\u6587\u6848"), React.createElement("option", null, "\u7B2C\u4E00\u955C\u53E3\u64AD"))), React.createElement(Field, {
    label: "\u4FEE\u6539\u65B9\u5411"
  }, React.createElement("select", {
    name: "tone"
  }, React.createElement("option", null, "\u66F4\u7B80\u6D01"), React.createElement("option", null, "\u66F4\u81EA\u7136"))), React.createElement(Tag, null, "\u4EC5\u4FEE\u6539\u5F53\u524D", ['抖音', '小红书'][platform], "\u7248\u672C"))), modal?.type === 'versions' && React.createElement(React.Fragment, null, React.createElement("div", {
    className: "lineitem"
  }, "\u5F53\u524D\u6837\u7247", React.createElement(Tag, null, "\u7B2C ", run.revision, " \u7248")), run.history.length ? run.history.map((v, i) => React.createElement("div", {
    className: "lineitem",
    key: i
  }, React.createElement("span", null, "\u7B2C ", v.revision, " \u7248 \xB7 ", v.content.title[platform]), React.createElement("button", {
    type: "button",
    onClick: () => {
      edit({
        ...demoContent(run.product),
        ...clone(v.content)
      });
      close();
      setToast('历史内容已恢复为新草稿，更新样片后生效');
    }
  }, "\u6062\u590D\u4E3A\u65B0\u8349\u7A3F"))) : React.createElement("div", {
    className: "empty"
  }, "\u9996\u6B21\u751F\u6210\uFF0C\u6682\u65E0\u5386\u53F2\u7248\u672C"), (run.copyHistory || []).map((v, i) => React.createElement("div", {
    className: "lineitem",
    key: 'draft' + i
  }, React.createElement("span", null, "\u6539\u5199\u524D\u4EBA\u5DE5\u7A3F \xB7 \u7B2C ", v.revision, " \u7248"), React.createElement("button", {
    type: "button",
    onClick: () => {
      edit(clone(v.draft));
      close();
      setToast('已恢复改写前人工稿');
    }
  }, "\u6062\u590D\u4EBA\u5DE5\u7A3F")))), modal?.type === 'facts' && React.createElement(React.Fragment, null, React.createElement("div", {
    className: "lineitem"
  }, "\u5546\u54C1", React.createElement("span", null, run.product.name)), React.createElement("div", {
    className: "lineitem"
  }, "\u89C4\u683C", React.createElement("span", null, run.product.spec)), React.createElement("div", {
    className: "lineitem"
  }, "\u6765\u6E90", React.createElement("span", null, run.product.files.join('、'))), React.createElement("div", {
    className: "notice"
  }, "\u672C\u5730\u793A\u4F8B\u4EC5\u4F7F\u7528\u5546\u54C1\u540D\u79F0\u4E0E\u5916\u89C2\u3002\u4EF7\u683C\u3001\u8BA4\u8BC1\u3001\u6027\u80FD\u6570\u636E\u672A\u7ECF\u786E\u8BA4\uFF0C\u4E0D\u5199\u5165\u8425\u9500\u6587\u6848\u3002")), modal?.type === 'product' && React.createElement(React.Fragment, null, React.createElement(Art, {
    type: db.products[modal.index].type
  }), React.createElement("div", {
    className: "lineitem"
  }, "\u5546\u54C1", React.createElement("span", null, db.products[modal.index].name)), React.createElement("div", {
    className: "lineitem"
  }, "\u89C4\u683C", React.createElement("span", null, db.products[modal.index].spec)), React.createElement("div", {
    className: "lineitem"
  }, "\u6765\u6E90", React.createElement("span", null, db.products[modal.index].files.join('、'))), React.createElement(Field, {
    label: "\u8865\u5145\u5546\u54C1\u56FE\u7247"
  }, React.createElement("input", {
    type: "file",
    accept: ".png,.jpg,.jpeg",
    onChange: e => {
      const f = e.target.files[0];
      if (!f) return;
      if (f.size > 20 * 1024 * 1024 || !/\.(png|jpe?g)$/i.test(f.name)) return err('请选择不超过20兆的商品图片');
      setDb(v => ({
        ...v,
        products: v.products.map((p, i) => i === modal.index ? {
          ...p,
          files: [...p.files, f.name]
        } : p)
      }));
    }
  })), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: "facts"
  }), "\u5DF2\u6838\u5BF9\u5546\u54C1\u5916\u89C2\u3001\u89C4\u683C\u4E0E\u4E8B\u5B9E\u6765\u6E90")), modal?.type === 'new' && React.createElement(React.Fragment, null, React.createElement(Field, {
    label: "\u5546\u54C1\u540D\u79F0"
  }, React.createElement("input", {
    name: "name"
  })), React.createElement("div", {
    className: "two"
  }, React.createElement(Field, {
    label: "\u5546\u54C1\u7F16\u53F7"
  }, React.createElement("input", {
    name: "code"
  })), React.createElement(Field, {
    label: "\u89C4\u683C"
  }, React.createElement("input", {
    name: "spec"
  }))), React.createElement(Field, {
    label: "\u5546\u54C1\u54C1\u7C7B"
  }, React.createElement("select", {
    name: "type"
  }, React.createElement("option", null, "\u65E0\u7EBF\u8033\u673A"), React.createElement("option", null, "\u5439\u98CE\u673A"))), React.createElement(Field, {
    label: "\u5546\u54C1\u8D44\u6599"
  }, React.createElement("input", {
    type: "file",
    accept: ".png,.jpg,.jpeg,.pdf,.docx,.txt,.mp4",
    multiple: true,
    onChange: e => {
      const files = Array.from(e.target.files);
      if (files.some(f => f.size > (/\.mp4$/i.test(f.name) ? 200 : /\.(pdf|docx|txt)$/i.test(f.name) ? 30 : 20) * 1024 * 1024 || !/\.(png|jpe?g|pdf|docx|txt|mp4)$/i.test(f.name))) return err('文件类型不支持或超限：图片20兆、文档30兆、视频200兆。');
      setModal({
        ...modal,
        files: files.map(f => f.name)
      });
    }
  })), modal.files?.map(n => React.createElement("div", {
    className: "lineitem",
    key: n
  }, n, React.createElement(Tag, null, "\u4EC5\u767B\u8BB0\u6587\u4EF6\u540D"))), React.createElement("label", {
    className: "check"
  }, React.createElement("input", {
    type: "checkbox",
    name: "rights"
  }), "\u6211\u62E5\u6709\u7D20\u6750\u4F7F\u7528\u6743")), modal?.type === 'unknown' && React.createElement(React.Fragment, null, React.createElement("div", {
    className: "notice"
  }, "\u6682\u672A\u53D6\u5F97\u5916\u90E8\u5B8C\u6210\u6216\u5931\u8D25\u8BC1\u636E\uFF0C\u4FDD\u6301\u5F85\u6838\u67E5\u4E0E \xA58.00 \u9884\u7559\uFF0C\u4E0D\u91CD\u53D1\u8BF7\u6C42\u3002"), React.createElement("button", {
    type: "button",
    onClick: () => {
      patchRun({
        status: '生成中',
        stage: 3,
        problem: null,
        unknownReservation: 0
      });
      close();
      setToast('已模拟收到完成证据，复用原请求继续合成');
    }
  }, "\u6F14\u793A\u6536\u5230\u539F\u8BF7\u6C42\u5B8C\u6210\u8BC1\u636E")), modal?.type === 'cancel' && React.createElement("div", {
    className: "notice"
  }, "\u505C\u6B62\u5C1A\u672A\u63D0\u4EA4\u7684\u6B65\u9AA4\u3002\u771F\u5B9E\u5916\u90E8\u8BF7\u6C42\u4ECD\u53EF\u80FD\u4EA7\u751F\u8D39\u7528\uFF0C\u53D6\u6D88\u4E0D\u7B49\u4E8E\u9000\u6B3E\u6216\u91CA\u653E\u672A\u77E5\u9884\u7559\u3002"), modal?.type === 'budget' && React.createElement(Field, {
    label: "\u9884\u7B97\u4E0A\u9650\uFF08\u5143\uFF09"
  }, React.createElement("input", {
    type: "number",
    name: "budget",
    defaultValue: run.budget
  })), React.createElement("div", {
    className: "bottom"
  }, React.createElement("button", {
    type: "button",
    onClick: close
  }, "\u8FD4\u56DE"), !['choose', 'versions', 'facts', 'unknown'].includes(modal?.type) && React.createElement("button", {
    className: "primary",
    type: "submit"
  }, {
    manual: '保存并继续制作',
    generate: '确认并生成',
    review: '确认并下载演示清单',
    rewrite: modal?.phase === 'candidate' ? '采用候选' : '生成改写候选',
    update: '确认更新样片',
    product: '确认并创作',
    new: '保存商品',
    cancel: '确认取消',
    budget: '保存预算'
  }[modal?.type] || '确认')))), React.createElement("div", {
    className: 'toast ' + (toast ? 'show' : ''),
    role: "status"
  }, toast));
}
ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(FlowApp, null));