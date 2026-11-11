# 后端当前运行边界

安装 requirements.txt，设置 DATABASE_URL 指向 PostgreSQL。开发可使用默认 SQLite，仅作本地功能测试；不证明 PostgreSQL 并发保证。

初始化与账号：在 apps/api 工作目录运行 `python -m app.accounts 用户名`。交互密码至少12字符。重复用户名会重置密码并撤销该工作空间会话。

运行 `uvicorn app.main:app --host 127.0.0.1 --port 8000`。同源前端登录 POST /api/v1/sessions，之后所有写操作提交 X-CSRF-Token。可用 GET /api/v1/sessions/current 恢复 token。

生产生成当前仍由 PROVIDER_NOT_CONFIGURED 阻断；不能把服务端保存能力视为完整生产能力。运行器/外部供应商接入须保留预算预留、已授权输入快照和独立人工审核。

上传：POST /api/v1/skus/{id}/sources，raw body，X-Filename URI编码文件名，X-Rights-Confirmed:true；文件保存到 AIGC_STORAGE_ROOT 私有目录。暂支持 PNG/JPEG/TXT/PDF/DOCX，MP4待媒体探测接入。TXT解析提供段落来源，其余格式明确返回未配置，不伪造解析成功。

当前开发登录限速为进程内，横向部署前需持久化共享限速。HTTP仅适用localhost；生产反代必须HTTPS以设置Secure cookie。

PostgreSQL 建表/升级必须执行 `python -m app.migrate`，使用版本 SQL、事务锁和 checksum；不要对已有生产数据库调用 create_all 代替迁移。001 是全新安装基线，旧开发 create_all 库需单独核对后建立基线，不会自动破坏或覆盖。

输入已增加 MP4（200 MB / 120秒 / 5个）和PDF/DOCX页/段解析。扫描PDF页标记OCR_REQUIRED，不假装已识别。删除先撤销访问，`app.deletion.cleanup_once`清理私有源/资产/导出对象；外部清除保持待核查。

2026-11-11 实现更新：
- 已有服务器配置就绪检查、请求输入快照、授权记录、幂等任务 admission；默认配置不全时仍阻断真实生成。
- 作品支持平台限定草稿、标题正文零媒体调用新版本、媒体 edit_run 入队、AI rewrite 候选与显式采用、完整历史媒体复用恢复。媒体编辑具体能力以 Worker handler/configuration 为准。
- 样片导出校验精确当前结果资产、完整槽位、hash和可见样片标识；下载重查事实与文件。发布导出仍受平台规则核验门禁。
- 上传已使用流式文件写入和在途大小/数量预留；文件真实格式验证后转正式source。解析通过独立 Python 进程，30秒超时、5MB输出限制；Linux提供CPU/内存硬限，Windows尚未实现OS级资源/网络隔离。
- 显式 PostgreSQL migration 已在本地开发容器应用并幂等重放。SQLite测试不能替代PostgreSQL并发证据。

登录限速已改为数据库持久化的IP＋账户双窗口（5次/60秒），所有API进程共享，429返回Retry-After。PostgreSQL执行003_login_rate_limits迁移；既有内存attempts仅兼容旧测试夹具，不参与鉴权。

列表新增 `order=created_desc` 与 `next_cursor`；续页须保持同order，不得同时使用cursor与offset。默认id_asc保持兼容。旧迁移记录created_at=null/created_at_known=false，不能解释为新建时间。档案列表的current_profile_id来自明确确认操作；selection_required=true表示旧档案需明确选择，客户端不得用列表末项推断。

管理员账单对账现提供本机 CLI：`python -m app.reconcile inspect` 与 `python -m app.reconcile import`。默认dry-run，显式`--apply`才结算；完整字段、实际命令及证据/usage边界见 [BILLING.md](BILLING.md)。金额已统一NUMERIC(18,8)，007迁移保留10位整数容量，不重算旧费用；无真实供应商账单不释放未知预留。

### 数据库租户引用约束（008）
生产启动前必须执行 `python -m app.migrate`；`initialize/create_all`只创建开发测试表，不安装生产生成列或租户复合外键，也不能替代迁移。008 从既有 JSON 引用生成只读列，引用 `(id,workspace)`；新写入/修改的 SKU、档案、作品、当前结果引用受到数据库隔离约束，允许同事务循环引用。历史数据不回填，外键明确保留 NOT VALID；迁移前可运行 `python apps/api/tests/audit_workspace_references.py` 只读统计异常。尚未覆盖 JSON 数组资产/来源引用、任务payload、外部调用及预算关联的复合键；目标kind与同SKU仍由领域服务校验。不得将此阶段称为全部数据库引用已规范化。
