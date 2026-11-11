# AIGC 营销工作台实现

依据产品/技术文档 v0.4，视觉基准为 `designs/aigc-studio-fresh`。项目处于开发与试用阶段。产品资料位于 `AIGC营销工作台_产品与技术文档_v0.4`，应用代码位于 `apps`。

## 本地运行

1. 安装 Python 依赖：`python -m pip install -r apps/api/requirements.txt -r apps/worker/requirements.txt`。
2. 在 `.env` 设置本地数据库 `POSTGRES_PASSWORD`，执行 `docker compose up -d postgres`。
3. 执行 `powershell -File scripts/run.ps1 migrate` 创建/升级数据库。
4. 设置 `PYTHONPATH=apps/api` 和同一 `DATABASE_URL` 后，运行 `python -m app.accounts 用户名`；密码通过交互输入，不放命令行。
5. 分别运行 `powershell -File scripts/run.ps1 api` 和 `powershell -File scripts/run.ps1 worker`。
6. 在 `apps/web` 运行 `npm ci`、`npm run dev`。默认生产模式，`?demo=1` 为明确独立的原型演示。

API/Worker使用同一私有存储目录 `runtime/storage`，不得将它作为静态网站发布。Worker真实调用还要求完整可信配置；仅启动进程不代表生成已启用。

## 验证

- 前端：在 `apps/web` 运行 `npm run build`、`npm run typecheck`。
- API：`PYTHONPATH=apps/api` 下运行 `python -m pytest apps/api/tests -q`。
- Worker：`PYTHONPATH=apps/api;apps/worker` 下运行 `python -m unittest discover -s apps/worker/tests -v`。
- PostgreSQL并发预算：`powershell -File scripts/run.ps1 budget-check`，创建随机测试schema并在完成后清理，仅测试本项目数据库。

Windows 沙箱可能阻断 TestClient 的 asyncio 回环 socket，需在允许本机回环的环境验证。本文列出验证方式，本次整理未重新运行应用测试。

## 公开范围

仓库包含产品需求与技术设计、交互原型、应用实现及测试代码。运行数据、凭据、真实商品产物和本地部署记录不公开。真实供应商调用需要独立配置与费用授权。

项目仍处于开发与试用阶段，生成结果须人工复核；商品保真、正式平台发布及生产容量尚不能据此视为通过。
