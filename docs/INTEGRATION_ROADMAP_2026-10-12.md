# ModelOps Platform · 统一集成与非 GPU 软件交付计划

**基线：2026-10-12；仓库：Benjamindaoson/ModelOps-Platform。**
本文件是对 `docs/IMPLEMENTATION_PLAN.md` 的执行补充，专门解决两个并行代码线合并后的平台完整性、测试和交付问题。**不以代码行数、UI 截图、Helm 渲染或 GPU Mock 成功作为完成标准。**

## 0. 当前事实（所有状态以对应提交 SHA 为准）

| 代码线 | 状态 | 证据 / 风险 |
|---|---|---|
| `main` Phase 1–5 | Canary / HPA/KEDA / Argo 参数 / 仪表盘 / 备份脚本已经提交 | 原提交 `f34dc73` 的 Go CI 编译失败，不能宣称完整实现 |
| **PR #14** 编译修复 | **已合并** `c149f266` | 源 PR 的 8/8 CI 通过；修改重复 EnginePort、Canary PVC API 类型、SGLang 端口 |
| **PR #13** 产品控制面 | **开放 Draft；与 main 冲突** | 73 个文件、33 次提交；FastAPI、Next.js、动态 Argo、OIDC、Postgres、命名空间 RBAC；最新分支 API / Console / Go-Python-Helm CI / kind 测试通过，但浏览器 E2E 有失败 |
| 真实 GPU Serving、训练、HA | 尚未验证 | 无真实 TTFT、TPOT、吞吐、显存、LoRA/QLoRA 完整作业记录 |

注意：2026-10-11 最新主分支提交标题为“complete Phase 1–5”，**提交标题不是验收结果**。本计划中的“完成”必须满足下方明确的 Gate。

## 1. 统一架构决策（冻结后开发）

| 责任 | 唯一权威来源 | 说明 |
|---|---|---|
| 产品账户、租户、ModelArtifact、DatasetVersion、审批、审计 | FastAPI + PostgreSQL | 数据库记录的是管理元数据，不等于真实模型权重验证 |
| 模型部署期望/实际状态、资源生命周期 | `ModelDeployment` CRD + Go Operator | 不允许 FastAPI、Helm `models[]` 和手动 Gateway 注册三套互相矛盾的权威状态 |
| FineTuneRun 执行状态 | Argo Workflow（Operator/Control API 查询） | 每个任务具有不可变参数、数据版本、独立工作目录与日志 |
| 模型文件、Adapter/Checkpoint、实验产物 | MinIO/S3 + MLflow Registry | 对象和版本可检索，并通过实测校验 SHA/大小；“已登记”不等于“已验真” |
| Web/CLI | 统一 Control API | UI 不直连 Kubernetes 管理令牌、LiteLLM master key、对象存储密钥 |
| Helm | 基础服务和 CRD **安装/升级** | 普通模型 CRUD、发布和回滚不要求重新编辑同一份 Helm Values |

## 2. 依赖顺序与执行门禁

### Gate A — 修复稳定基线（P0，最先）

**已完成：** PR #14 通过 8/8 CI 并合入 main。

**继续验证：**
- 在合并后主分支执行 `cd operator && go test ./...`，不能只测 builder/engine 部分包。
- 对新提交的 Canary、HPA/KEDA、Gateway 和 Argo Controller 增加真实失败分支测试；已有指标必须区分“编译通过”与“控制器执行正确”。
- 确认最新 main CI 全绿、无编译错误，保存 SHA 和 workflow run ID。

**Gate A PASS：** main 编译/单测均通过，并保留失败根因与对应回归测试。

### Gate B — 只保留一条集成线，将 PR #13 完整融入 main（P0）

**执行方式：** 不再复制新平台、不另开重复产品线；以现有 PR #13 分支作为唯一集成分支，将最新 main 合入该分支。不能使用 `-X ours/theirs` 全局粗暴覆盖。

**必须人工合并的语义：**
1. `operator/internal/controller/modeldeployment_controller.go`：**保留 main 的 Canary、HPA/KEDA、PDB、下载状态、Gateway 逻辑**，再吸收 PR #13 的 fail-closed Gateway 状态与最小权限约束。
2. **所有** `r.Create/r.Update/controllerutil.SetControllerReference/RegisterModel/DeregisterModel` 的失败必须正确返回错误或写入 `Degraded` 状态并重试；禁止 `_ =` 吞掉关键错误。
3. `ModelDeployment` status 以实际 observedGeneration、就绪副本、Gateway 验证为准；不能把 Pod Ready 当作 Gateway 可路由成功。
4. 修复 `BuildArgoWorkflow` 与新动态 `WorkflowTemplate` 的协议：**参数名唯一规范**（当前 main 是 `base-model` 等连字符，PR #13 是 `base_model` 等下划线），templateRef 应匹配实际 Helm 创建的资源。保留旧 API 时必须显式做映射和兼容测试。
5. 避免 Helm 模型部署和 CRD 模型部署重复写同一个 Gateway 路由；决定唯一模型生命周期写入口。

**Gate B PASS：** 无 Git 合并冲突，Go/Python/Next build/Helm 全绿，API 与 Operator 状态协定用测试固定；PR #13 可转 Ready，最终合并进 main。

### Gate C — 真正的 Control Plane 和状态一致性（P0）

交付：
- 有版本的 `ModelArtifact`、`DatasetVersion`、`DeploymentRevision`、`FineTuneRun`、`EvaluationResult`、`ReleaseApproval`、`AuditEvent` REST API；租户级别的访问和隔离。
- 完整的模型创建/更新/删除、版本查询、CAS（并发修改保护）、可审计审批；对象存储 Artifact Hash 须由可信 Worker 核验。
- K8s API 成功但 PostgreSQL commit 失败时：设计 Outbox/补偿/后台协调任务，消除“集群已有资源而数据库显示失败”的孤儿状态；更新操作有幂等请求 ID；删除有 finalizer/软删除明确语义。
- ModelDeployment/Argo 真实状态回读；API 超时、Gateway 不可达、节点失联不会被报告为 Ready。
- 给 FastAPI 增加持续运行的 Reconcile/Recovery 机制，而不是只依赖同步 POST。

**Gate C PASS：** 在真实 kind 中，通过 API 创建 CRD、观察 Controller 创建 Deployment/Service/PVC、状态可查询、可停启/删除，断开 Gateway/DB/重启 API 等故障后可恢复或明确拒绝；两个租户互不可见。

### Gate D — 动态微调闭环（P0，不以 GPU 为借口跳过纯软件）

交付：
- 每个 FineTuneRun 独立模型 revision/digest、dataset revision/split/hash、method (Full/LoRA/QLoRA)、LR、batch、epoch、LoRA rank/alpha、grad accumulation、GPU/CPU、quota、quality threshold。
- Dataset Manifest 同时包含 `train.json` 和 `heldout.jsonl` 的 SHA；在作业启动前校验，杜绝训练集泄漏与固定示例问答评估。
- 动态 Argo WorkflowTemplate 跑真实 `prepare → validate-data → train → merge → evaluate → gate → publish`，每一步有重试/超时/故障状态；独立 Artifact 版本进入 MLflow 和 MinIO。
- 取消/重试/断点、日志、Checkpoint 与两项不同超参数任务并发隔离；失败/低指标不注册或上线为“已通过”。
- 独立 ReleaseApproval 必须在质量证据校验成功后生效，非 GPU 可以使用**明确标注**的 CPU 小模型作完整流程验证；不能把 CPU Stub 产物当作真实训练。

**Gate D PASS：** 两个不同参数 Run 的 Argo 参数与存储目录互不覆盖；缺模型/错误 checksum/训练失败/质量不足全部明确 FAIL，CPU 小模型实际运行一次 Train → Eval → Publish 并可回读产物。

### Gate E — 模型发布、Canary、回滚、自动扩缩容（P0/P1）

交付：
- 所有路由用稳定对外 `model_name`；确保 LiteLLM 是否真的按指定权重将同一模型名路由至两套后端，**不能仅分别注册 `model` 和 `model-canary` 就声称灰度流量已生效**。
- Canary 流量比例可通过真实请求统计测定；只在候选 Ready、Gateway 注册成功、质量批准有效时开放；不健康自动回退稳定版本。
- HPA / KEDA 互斥规则、指标来源与缺失时的回退；禁止出现两个扩缩容控制器争抢同一副本数。
- Scale、Promote、Rollback、Delete 后 Deployment、Service、Gateway 注册与 PostgreSQL Revision 同步；失败重试幂等。
- Canary PVC/镜像/资源命名唯一，不复用错误的稳定模型缓存。

**Gate E PASS：** CPU 模拟推理服务发起可辨识 HTTP 请求，验证 0/10/50/100% 流量分配和候选故障后的回退；对 429、连接失败、重启、删除至少各一个可重放故障测试；运行时真实观测，不靠 YAML 模板推断。

### Gate F — Web 控制台、登录与权限（P0）

交付：
- 现有 Next.js 首页/模型中心/部署中心/训练中心/数据中心/评估/审批/审计/设置统一真实 API。
- 页面状态、表单校验、筛选、分页、错误反馈、历史版本、细粒度审批、异步作业进度、停止与重试。
- 生产 OIDC Authorization Code + PKCE、HttpOnly Secure 会话，服务端权限校验；Dev token 只允许显式开发环境。使用本地 OIDC Test IdP 检查完整登录、过期、拒绝、不同租户身份。
- 响应式桌面/移动端，页面无死链接；真实数据操作经过 API，失败不做“成功”toast。
- 修复 PR #13 当前失败的浏览器 E2E（失败路径错误提示定位不稳定），增加两个租户、版本审批、错误回滚测试。

**Gate F PASS：** Playwright 全量浏览器 E2E 通过；用户仅通过界面完成模型登记、数据登记、CPU 测试部署、查看版本与错误、训练任务提交/查询、审批及回滚。

### Gate G — 安全、可观测性、备份恢复和交付（P0/P1）

交付：
- Namespace Scope 的 Go Operator 和 Argo 任务、最小 Kubernetes RBAC/ServiceAccount、SecretRef、NetworkPolicy、配额、租户审计；实际 `kubectl auth can-i` 证明跨 Namespace 与 secret 读取被拒绝。
- OIDC RBAC 验证、API 限速、异常审计、输入 Schema/Model Artifact 安全校验、控制 API 不可携带集群管理员凭据到前端。
- 5 个 Grafana JSON 看板逐个验证 PromQL/数据源/标签可采集；GPU 指标可标记未接入，不能画静态虚假图。
- 实际执行 `ops/backup.sh` → 删除测试数据 → `ops/restore.sh`，校验 PostgreSQL / 对象存储 / K8s 配置恢复一致性；备份密钥加密、恢复演练具备 RPO/RTO 记录。
- OTel/Prometheus/DCGM/请求追踪/SLO 告警联动；离线时报告 `NoData` 而不是健康。
- 镜像安全扫描、SBOM、不可变镜像 digest、Alembic migration rollback、可复现本地 Compose 与 kind 启停。

**Gate G PASS：** 真实 Kind 上端到端运行、租户 RBAC 拒绝、故障注入、备份/恢复、升级/回滚全部复测并留存报告。

### Gate H — 非 GPU 软件发布验收（最终合并标准）

```text
H1: go test ./...                     所有 Operator 包通过
H2: helm lint/template                所有 profile + 动态 Argo Workflow 正确
H3: pytest                             API/微调/证据/安全/回归测试通过
H4: Next.js build + Playwright E2E     桌面/移动端、管理/拒绝/错误路径通过
H5: CPU kind E2E                       UI→API→CRD→Operator→Gateway→CPU endpoint→回滚
H6: State & security                   并发、幂等、跨租户拒绝、Gateway/DB 故障恢复
H7: Recovery & delivery                备份/恢复、升级迁移、日志与审计
```

只有 H1–H7 均通过，才能使用 **“非 GPU 软件平台达到工程交付 Gate”**；不等于生产环境的多节点 HA 认证。

### GPU / 多节点证明（独立，不计作 H1–H7 的已通过项）

- GPU Serving：同权重 vLLM/SGLang，TTFT/TPOT、P50/95/99、Goodput、KV Cache、AWQ/GPTQ、Batch/Prefix Cache、显存与利用率，保存真实基准。
- GPU Training：LoRA、QLoRA、Checkpoint、Heldout 评估、真实 Adapter/模型权重、Train→Serve、质量变化。
- 多节点/多硬件：GPU Scheduler、HPA/KEDA、Pod 恢复、节点失联、TensorRT-LLM、ASR/TTS 实机、资源成本和 HA。
- 管理类 JD（团队带领年限、绩效、招聘）需要实际经历，不可由代码替代。

## 3. 当前优先级与并行约束

**最高优先：A → B**。B 没完成时不添加新的互相竞争的模型控制器或 UI。B 之后 **C + F 可并行，但由 C 的接口契约控制 F**；D 需要 C 的模型/数据版本；E 需要 C + D 的发布审批；G 横向贯穿所有 Gate；H 最后。

建议实际工作包：
1. **PR A**：主分支编译修复验收（PR #14 已完成）；
2. **PR B**：PR #13 解决冲突、保留 Canary/HPA，统一 Argo 参数协议；同一现有开发分支，不另起重复分支；
3. **PR C**：控制面状态一致性与全 Controller envtest；
4. **PR D**：数据/动态训练/独立发布门禁；
5. **PR E**：Canary 权重、可审计回滚和 KEDA 故障注入；
6. **PR F/G**：Web/SSO/E2E、跨租户安全、备份/恢复、监控；
7. **最终 Gate H**：non-GPU 交付证据、变更记录与版本化 release。

**每个工作包的 Definition of Done**：实际源码修改 + 正反测试 + CI 绿色 + 运行证据链接 + 限制披露 + 无已知 P0 阻断。未通过则不标“完成”。

## 4. 和目标 JD 的关键产出

| 业务线 | 软件层可交付证据 | 还必须另行实测 |
|---|---|---|
| 模型托管/推理 | 模型 registry、Version/Canary/rollback、Gateway/Operator/多引擎、SLO 仪表盘 | 真 GPU/多硬件吞吐与时延、KV/连续批处理/量化收益 |
| 微调 | DatasetVersion、参数化 Argo、LoRA/QLoRA、Checkpoint、Heldout、MLflow、审批 | 真实训练的 Loss/质量/显存/速度、训练后的 Serving |
| 平台运维 | Namespace RBAC、审计、备份、恢复、故障注入、CI/CD、Web 自助操作 | 真实多节点高可用与故障恢复的生产 RTO |
| 团队交付 | ADR/任务验收/测试矩阵/代码评审/发布证据 | 真实人员管理经历不由仓库证明 |

**最终判断：当前不是只差 GPU。** 优先解决集成冲突、动态工作流参数协定、控制面一致性、Canary 真正加权路由和浏览器全链路，以及无 GPU 的安全/故障恢复验收。
