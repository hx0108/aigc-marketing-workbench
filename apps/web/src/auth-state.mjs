export function validateAuth(mode, username, password, confirmation) {
  if (!username || username !== username.trim() || username.length > 200 || /[\x00-\x1f\x7f]/.test(username)) return '请输入有效账号，首尾不能有空格';
  if (!password) return '请输入密码';
  if (mode === 'register' && password.length < 12) return '密码至少需要 12 个字符';
  if (password.length > 1024) return '密码不能超过 1024 个字符';
  if (mode === 'register' && password !== confirmation) return '两次输入的密码不一致';
  return '';
}
export function authErrorMessage(error) {
  const code = typeof error.detail === 'object' ? error.detail?.code : error.detail;
  if (error.status === 409 || code === 'USERNAME_TAKEN') return '此账号已被使用，请换一个账号或登录';
  if (error.status === 401) return '账号或密码不正确';
  if (error.status === 429) return '尝试次数较多，请稍后再试';
  if (error.status === 422) return '请检查账号和密码格式';
  return '暂时无法连接服务，请稍后重试';
}
