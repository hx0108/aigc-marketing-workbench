import { request } from './api';
const {useEffect,useState}=React;

export function MerchantKeys(){
 const [status,setStatus]=useState(null),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
 useEffect(()=>{let active=true;request('/merchant-keys').then(data=>{if(active)setStatus(data)}).catch(()=>{if(active)setMessage('读取配置失败')});return ()=>{active=false}},[]);
 async function save(event){
  event.preventDefault();
  const form=event.currentTarget;
  const fields=Object.fromEntries(new FormData(form));
  setBusy(true);setMessage('');
  try{
   await request('/merchant-keys',{method:'PUT',body:JSON.stringify(fields)});
   form.reset();setStatus({configured:true,cap:fields.cap});setMessage('已保存，可点击一键生成。');
  }catch(e){setMessage(typeof e.detail==='string'?e.detail:'保存失败，请检查密钥和累计费用上限。')}
  finally{setBusy(false)}
 }
 return <details className="panel"><summary>{status?.configured?'管理我的 MiniMax API Key':'绑定我的 MiniMax API Key'}</summary><form onSubmit={save}>
 {Object.entries({minimax:'MiniMax 中国站 API Key（文案、图片、视频和配音）'}).map(([key,label])=><label className="auth-field" key={key}>{label}<input required name={key} type="password" autoComplete="off" maxLength={4096}/></label>)}
 <label className="auth-field">我的累计费用上限（元）<input required key={status?.cap} name="cap" type="number" min=".01" step=".01" max="100000" defaultValue={status?.cap||''}/></label>
 <button type="submit" disabled={busy}>{busy?'正在保存…':'保存密钥'}</button><span role="status">{message}</span></form></details>
}
