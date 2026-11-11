# 本机管理员账单对账

入口为 `python -m app.reconcile`，没有 HTTP 写入接口。仅由持有本机数据库运维凭据、已核对供应商账单原件与调用映射的管理员运行；普通网页账号不能导入费用。命令拒绝非本机 PostgreSQL 地址。不会调用模型、查询供应商、推算汇率或自动生成账单。

## 精度与证据边界

金额统一使用十进制定点 **NUMERIC(18,8)**：10 位整数＋8 位小数。`0.001306` 元与 `0.00000004` 元均精确保留；`0.000000001` 等超精度值拒绝，不静默四舍五入。007 迁移仅扩展存储精度，不重算既有预留、账目或收费。

- 原始 usage 是用量事实；`usage × 价格`是费用估算，供应商计费周期、缓存分类、优惠及舍入规则未核验前不能当账单。
- 账单映射必须声明 `evidence_kind=supplier_bill`；`usage_estimate` 被拒绝。最终收费以管理员核验的供应商账单／最终未收费证明为准；代码的文件 hash 不等于供应商真实性签名。
- 当前此入口只接收 **CNY 增量金额**，不是累计总额。其他币种拒绝，不猜测转换价格。
- `final=false` 只结算本行已确认增量，余下预留保留；`final=true` 必须有供应商最终结清证据，才释放余额。任务取消、响应成功、usage 返回均不能替代最终证据。

## 实际命令

在已设置 `DATABASE_URL` 指向本机 PostgreSQL 的运维终端，从仓库根目录执行：

```powershell
$env:PYTHONPATH = 'apps/api'
python -m app.migrate
python -m app.reconcile inspect --workspace '<工作空间ID>' --budget-id '<预算ID>'
```

`inspect` 只输出调用ID、请求hash、上界、剩余预留及状态，不输出业务资料或密钥。超过100条时按 `next_after_call_id` 继续传 `--after-call-id`。

管理员从供应商账单中核对每行对应调用，并创建本地 JSON 映射；以下是结构模板，不是真实账单：

```json
{
  "schema_version": 1,
  "provider": "deepseek",
  "provider_account": "供应商账户标识（非密钥）",
  "bill_id": "供应商账单ID",
  "workspace": "工作空间ID",
  "currency": "CNY",
  "evidence_kind": "supplier_bill",
  "amount_semantics": "incremental",
  "evidence_sha256": "账单原件的64位小写SHA256",
  "lines": [{
    "line_id": "供应商账单行ID",
    "budget_id": "预算ID",
    "call_id": "inspect返回的调用ID",
    "request_hash": "inspect返回的64位请求hash",
    "amount": "0.00130600",
    "final": false
  }]
}
```

金额必须为字符串，`final` 必须为 JSON 布尔值。计算原件摘要：

```powershell
(Get-FileHash -LiteralPath 'C:\private\provider-bill.csv' -Algorithm SHA256).Hash.ToLowerInvariant()
```

先预检；默认不会归档证据或更改账本：

```powershell
python -m app.reconcile import --manifest 'C:\private\bill-map.json' --evidence 'C:\private\provider-bill.csv' --reviewed-by 'HX'
```

核对输出的调用、增量金额、最终标记及证据hash后，显式应用：

```powershell
python -m app.reconcile import --manifest 'C:\private\bill-map.json' --evidence 'C:\private\provider-bill.csv' --reviewed-by 'HX' --apply
```

证据默认保存在 `runtime/billing-evidence/<sha256>.evidence`（可用 `AIGC_BILLING_EVIDENCE_ROOT` 指定受控私有目录）；原件不移动、不覆盖，没有网页下载路由。原始证据、receipt与cost event应一并备份。

## 一致性与异常

同一供应商／账户／账单／行组成唯一事件；原样重放不重复记账，修改金额、调用或证据hash的重放拒绝。导入先校验全部行，再同事务结算；跨预算、跨空间、请求hash不符、缺失证据或金额非法均拒绝，不清空未知预留。

实际账单累计金额超过该调用授权上界时仍如实记账，并创建 `budget_hold`；后续预留返回 `BUDGET_HELD_FOR_REVIEW`，需管理员复评供应商与价格授权。本命令不自动解冻，也不把真实超账截断成上界。费用结清只改变费用状态，不把未知生成结果伪造为完成。

验证使用合成账单与独立测试schema；未对真实预留执行无证据结算。原始usage计价自动适配尚未作为账单导入渠道开放。
