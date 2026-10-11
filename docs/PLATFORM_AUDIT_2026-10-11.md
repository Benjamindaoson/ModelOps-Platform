# ModelOps Platform — 企业级平台完整性审计（2026-10-11）

> **当前结论：不是“除了 GPU 就完成”。** 当前是可复用的 Kubernetes-native LLMOps Engineering Preview，而不是完整、可交付的企业自助 ModelOps 平台。审计时 main 509 个文件，其中大多数上游移植；必须区分继承代码、我们自己的提交、测试通过与真实运行结果。

## 1. 验收口径与完成度

以「产品完整性 + 端到端功能 + 可运维性 + 安全 + 可复现证据」评估，而非依据文件数量或 README 功能列表。

| 维度 | 权重 | 当前成熟度（人工审计估计） | 加权 |
|---|---:|---:|---:|
| K8s/Helm 部署基础 | 10 | 75% | 7.5 |
| 模型 Serving Control Plane | 15 | 45% | 6.75 |
| 统一 Model Registry / Revision 生命周期 | 10 | 20% | 2 |
| 微调编排、数据准备、评估、发布 | 15 | 35% | 5.25 |
| 自助 Web 管理界面 / 产品 API | 10 | 10% | 1 |
| 数据资产管理、质量、追溯与权限 | 10 | 25% | 2.5 |
| 监控、SLO、可用性、故障处置 | 10 | 50% | 5 |
| 多租户安全、密钥及 RBAC | 10 | 20% | 2 |
| 测试、CI/CD、交付与审计 | 10 | 75% | 7.5 |
| **合计（不把 GPU 容量与实际训练结果算入要求）** | **100** |  | **39.5/100** |

本表是缺口优先级工具，不是自动测量数值。代码搭建层面大致 60%；扣掉未贯通产品闭环和实测后，非 GPU 平台完整性 **约 40%**；生产就绪性 **约 20%**。多 GPU/模型优化缺乏实际试验会进一步拉低 JD 技能证明度。

## 2. 已有基础与验证层级

| 功能 | 代码位置 | 实现来源/状态 | 当前最高证据 |
|---|---|---|---|
| K8s umbrella Helm + CPU LiteLLM + PostgreSQL | `charts/kube-llmops-stack/` | 主要上游继承 | CPU-kind 安装、HTTP 健康、卸载真实 PASS |
| LLMPlatform/ModelDeployment/FineTuneRun CRD | `operator/api/v1alpha1/` | 上游 + 部分自研 | Go builder/webhook单测，未完成真实 Operator E2E |
| vLLM、SGLang、TEI、llama.cpp | `charts/.../charts/`、`operator/internal/builder/` | 上游 Chart；SGLang Operator 增强 | Helm/Go 构造，真实 GPU 模型未启动 |
| LiteLLM 动态模型 Gateway | `operator/internal/gateway/` | 上游 | 客户端代码与测试，未验证完整 model registration |
| KEDA、Prefix Cache、路由、P/D 分离 | Helm 模板/引擎参数 | 上游 | 配置/渲染，未验证性能收益和故障恢复 |
| 微调 LLaMA-Factory/Argo/MLflow | `charts/.../finetune/` | 上游 + ModelOps 新的执行与验证闸门 | WorkflowTemplate 渲染、评估脚本单测，未真实训练 |
| PEFT merge、holdout、质量门禁 | `pipelines/training/`、`pipelines/evaluation/` | ModelOps 自研 | 合同单测（使用显式测试替身），不等于实训 |
| 观测系统 | `charts/.../observability/` | 上游 | 仪表盘和 Prometheus 配置，缺生产 SLO 实测 |
| 推理基准评测 | `benchmarks/inference/` | ModelOps 自研 | CLI/数据比较测试，暂无 TTFT/TPOT 实测 |
| 多模型 API smoke | `ops/smoke.py` | ModelOps 自研 | Stub HTTP 协议测试，ASR/TTS 模型未接入 |
| Headlamp UI | `plugins/kube-llmops-portal/src/` | 上游 | 只有 Service Links 与 Monitoring 两个页面 |
| 生产密钥/预检 | `ops/preflight.py`、`charts/.../litellm/` | 上游 + ModelOps 增强 | 部分 Secret 改善；仍存在权限/组件默认凭据 |
| CI、镜像发布 | `.github/workflows/` | ModelOps | main 8/8 CI；CPU kind；部署 Runner Docker 发布 |

## 3. 直接从源码发现的阻塞

### P0-A：控制台只有两个页面

`plugins/kube-llmops-portal/src/index.tsx` 仅注册 `/services` 和 `/monitoring` 路由。`ServiceLinksPage` 打开固定端口，`MonitoringPage` 使用 HTTP iframe 展示 Grafana。这不满足独立 ModelOps 产品所需的模型、部署、数据、训练任务、注册版本、评测、成本、租户权限、审计、发布回滚等自助功能。

### P0-B：FineTuneRun 配置并非真正按任务参数化

`operator/internal/controller/finetune_template_contract.go` 拒绝单个任务的 epochs、batch、lr、LoRA rank、GPU/内存、评测配置覆盖。原 `kubectl-llmops finetune create` 默认总会写入这些字段，导致自然用户入口产生失败的 CR。P0 hotfix 分支修正默认提交语义并明确拒绝不可应用的选项；真正的 Argo 参数化/隔离仍未实现。

### P0-C：微调链路还需要真实软件集成验证

上游 `configmap-train.yaml` 将 QLoRA 写成 `finetuning_type: qlora`，而 LLaMA-Factory 应使用 LoRA + 4-bit 量化。源码改造的 `train.json`/留出集校验和 PEFT merge 已有，但 MLflow Register -> 独立权重 -> Canary -> 回滚没有非 mock 全流程通过记录。
此外，上游示例的 HuggingFace 数据来源只产生 train.json，默认没有独立 heldout.jsonl，当前真实工作流会失败，这是应被正面解决的**软件数据准备缺口**，不应该算作单纯缺 GPU。

### P0-D：明文密钥和 cluster-admin

上游 LiteLLM ConfigMap 的 `general_settings.master_key` 和 `database_url` 使用 Helm 明文值，虽然 Pod env 部分已改为 Secret，仍泄漏到 ConfigMap。P0 hotfix 改为 `os.environ/...` 引用并增加 Helm 回归测试。但其他 MinIO、MLflow、Keycloak、Langfuse 等可选服务还存在示例凭据、明文值和硬编码。
`operator/charts/kube-llmops-operator/templates/rbac.yaml` 仍绑定 `cluster-admin`；生产要拆分 bootstrap 与运行权限，制定 namespace 最小权限。

### P0-E：发布和控制平面状态尚未一致

`ModelDeployment` CRD 有 Canary 字段、CLI 有 promote/rollback；但 `operator/internal/controller/modeldeployment_controller.go` 没有根据 CanarySpec 创建对应候选副本和加权路由。该控制器注册 Gateway 失败仅 log.Error，不强制改变 Ready 状态。
`operator/cmd/main.go` 若缺 GATEWAY_URL 则使用 NoopClient，可能使系统缺少真实 Gateway 注册仍看起来正常。需要单一发布状态机、Revision、真实 Gateway 探针和失败回滚。

### P1-F：端到端 CI 范围偏窄

主 CI 的 `operator-contracts` 只覆盖 api/engine/builder/gateway/helmbridge/CLI，不运行所有 Controller envtest。CPU Kind 工作流只验证 LiteLLM/PostgreSQL 的 Pod Ready 与健康接口，没有测试 Operator、模型下载、ModelDeployment、FineTuneRun、MLflow、ASR/TTS 或完整 Gateway 注册。8/8 CI 不代表所有平台功能验收通过。

### P1-G：没有统一的版本化模型资产体系

现有 CRD 可以指定 model source，但缺少完整模型/Adapter/Dataset 注册版本、不可变 Artifact Digest、产物归属、审批审计和自动推广状态。MLflow/MinIO 的部署模板存在，并不等价于完整注册中心的产品 API 与 UI。

### P1-H：Agent/CUDA/多硬件技术深度缺证据

没有实现自己的 CUDA Kernel、量化推理算子、KV Cache 调度引擎或 TensorRT-LLM Adapter；主要使用 vLLM/SGLang 参数与 K8s 模板。不能把上游引擎的性能实现写为 ModelOps 原创成果。

## 4. 和 JD 的逐项对应

| JD 职责 / 要求 | 仓库能证明的部分 | 尚缺的能力与证据 |
|---|---|---|
| 模型托管：LLM、Embedding、ASR、TTS、多硬件 | vLLM、SGLang、TEI、llama.cpp Chart/Operator | ASR/TTS 一等适配器；真实模型上线；多硬件兼容与 HA |
| 推理优化：TTFT、KV Cache、Continuous Batch、量化 | 基准工具、vLLM/SGLang 配置与路由 | 真实 A/B、显存、吞吐、质量、硬件限制；内核/框架二次开发 |
| vLLM/TensorRT-LLM/SGLang 集成 | vLLM/SGLang 初步集成 | TensorRT-LLM 缺；两个引擎未在实机完成可比试验 |
| 监控/故障处理 | Prometheus、Grafana、DCGM、KEDA 模板、smoke | 实际采集/告警、故障注入、RTO/MTTR、容量规划 |
| 安全/弹性生产 | Docker、K8s、部分 Secret/NetworkPolicy/PDB | RBAC、审计、限流、多租户、API 配额、恢复演练 |
| 端到端微调和领域适配 | LLaMA-Factory/Argo/PEFT merge/eval gate | 可参数化任务、数据注册、真实 LoRA/QLoRA、独立评测 |
| 训练到 Serving | 上传与 MLflow 注册代码、Canary 工作流 | 可靠模型版本/完整性/审批、真实部署和回滚 |
| 分布式训练、Accelerate | 依赖上游 LLaMA-Factory，Argo Job | FSDP/DeepSpeed/Ray/Accelerate 的自主流水线与多节点证据 |
| Python/CUDA/HPC | Python 工程、模型 Runtime 集成 | CUDA Kernel、GPU Memory/SM 优化、Profiling 等硬核经历 |
| AWS/GCP/Azure | Terraform/部署脚手架 | 云端真实部署、GPU Auto Scaling、安全网络、成本治理 |
| AI 原生研发 | 仓库开发规范与基础自动化 | 可靠 AI SRE/优化 Agent、结构化轨迹/评估 |
| 团队管理交付 | 实施计划、PR、CI | 人员招聘辅导/绩效/3 年团队管理不能由代码证明 |

## 5. 接下来必须完成的可验收阶段（先不需要 GPU）

| 门禁 | 工作范围 | 验收定义 |
|---|---|---|
| P0-1 | 安全/配置修正 | QLoRA/Key/CLI/训练集修复 + 回归 CI；所有 Secret 从 ConfigMap 清理 |
| P0-2 | 统一 ModelOps Control API | Model/Dataset/TrainJob/Deployment/Revision 统一资源 API、状态机、事件、模型校验 |
| P0-3 | 真正的 Web 控制台 | 登录/租户、模型中心、训练任务、部署发布、评测、监控与权限页面；有真实 API 数据和 E2E |
| P0-4 | 动态 Argo FineTuneRun | 每次 Run 可配置模型/数据/LoRA/GPU/超参；校验资源限额、版本与训练产物 |
| P0-5 | Gateway+Canary+Rollback 一致性 | 两条部署路径统一、候选版本运行、审批/健康检查、失败一致性、可重放事件 |
| P0-6 | 最小权限与密钥治理 | 拆分 cluster bootstrap 及 Runtime RBAC、Secret、SSO/RBAC、NamespaceQuota、审计日志 |
| P1-1 | 无 GPU 的真正系统集成 | kind + Operator + CRD + 模拟/CPU 小模型 + Gateway + TrainJob Argo stub + rollback API/状态 |
| P1-2 | 可观测与错误注入 | 模型和任务全链路 trace、SLO/告警、网络/进程故障和恢复验证 |
| P1-3 | 稳定交付与测试 | Go controller envtest、UI/API E2E、Helm OCI/SBOM、镜像版本、GitOps、升级/数据迁移 |
| GPU-1 | 真正量化、Batch、KV、推理系统比较 | RTX 3090 及可用更高规格 GPU 的真机性能对照 |
| GPU-2 | LoRA/QLoRA/FSDP 等微调和推广 | 真实模型 checkpoint、准确率变化、部署验证 |
| Cluster-1 | 多节点可靠性 | 真实多 GPU、多节点容错、自动扩缩容、资源/成本优化 |

验收政策：`T0 源码`、`T1 静态`、`T2 CPU 集成`、`T3 GPU Serving`、`T4 GPU Training`、`T5 HA` 严格分离。默认禁止把 T1/T2 文档或 Mock 结果写成生产指标。

## 6. 当前小结

**ModelOps 基础框架存在，但自助平台尚未建成。** 继续开发不应优先加 RAG 或新的 Agent，而应先完成五个关键平台闭环：统一资源/版本管理、前端与控制 API、动态训练/产物评估、可审计发布回滚、安全隔离。再投入 GPU 性能优化，才有资格完整对应目标 JD。
