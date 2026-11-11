# 登录 / 注册布局评审

沿用 `designs/aigc-studio-fresh` 当前原型及 `apps/web/src/style.css` 的视觉语言：Microsoft YaHei / PingFang SC，品牌色 #126b68、主按钮 #17262c、底色 #f4f6f7、分隔线 #e8ebed、10px 卡片与 7px 按钮圆角。仅调整信息布局。没有修改原型源文件。

- A 居中简洁：聚焦账号操作，留白充足。
- B 左右分栏：左侧单幅商品示意与产品价值，右侧表单。
- C 作品展示：错位双作品卡分别表达抖音和小红书定位，右侧表单。

浏览器入口：`http://127.0.0.1:4174/?auth-preview=1`，可用顶部按钮切换 A/B/C。`&mode=register` 直接打开注册态。预览使用真实认证接口；注册会创建真实账号及独立工作区，不赠送生成预算。表单支持账号、密码、确认密码、显示/隐藏、请求锁、错误提示及成功登录。预览登录成功后通过链接进入工作台；实际登录门禁成功直接进入工作台。

六态由同一 AuthScreen 组件呈现，并非单独静态复刻。原型耳机图仅作 CSS 设计示意，不表示真实生成结果；未使用用户私有商品照片。用户最终选择 B 左右分栏，默认正式门禁采用 B；A/C 保留为评审备选。

实现：`apps/web/src/AuthScreen.jsx`、`auth.css`、`auth-state.mjs`。入口 `index.html` 为本机评审导航。

验证：npm --prefix apps/web run typecheck / build 通过；node --test apps/web/src/auth-state.test.mjs 为 3 passed；python scripts/verify_auth_visual.py 验证六态截图、三布局390px无横向溢出、确认密码错误、显示隐藏、切换清空密码、无浏览器异常。截图位于 screenshots/。视觉脚本未提交认证请求；真实HTTP/Chrome注册登录证据见 scripts/verify_auth_http.py（主agent执行）。

最终 B 版验证：tsc、Vite build 及前端17项契约通过；API全量125项及15子测试通过。scripts/verify_auth_http.py --browser 在独立数据库/回环服务实际验证默认B布局、注册、登录、刷新会话、工作区隔离与退出失效。4174已重启加载新注册接口，ready正常；正式域名仍在部署中。
