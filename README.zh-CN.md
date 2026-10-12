# ModelOps Platform

**企业级 AI 模型训练、托管与推理优化一体化平台**

[English](README.md) | [项目架构](ARCHITECTURE.md) | [GitHub Actions](https://github.com/Benjamindaoson/ModelOps-Platform/actions)

一个面向企业内部 AI 团队的 Kubernetes 原生模型基础设施平台，统一实现 **模型注册 → 微调训练 → 独立评估 → 部署托管 → 推理性能测试 → 监控 → 灰度发布与回滚**。它不是聊天机器人、Agent 应用或单纯的 API 中转服务；业务应用通过模型网关使用平台托管和外部供应商提供的模型。

> **当前为 Engineering Preview，不是已完成生产验收的商业平台。** 真实 FastAPI 控制面、Next.js 管理后台、Go Kubernetes Operator、Argo 训练编排、网关及监控基础设施已有代码与部分 CI 证据，但不能凭这些宣称已经完成真实 GPU 推理加速、LoRA/QLoRA 训练效果、多节点高可用或企业生产部署。

## 五大功能模块

| 模块 | 已建设的主要软件能力 | 还需要的独立验收 |
|---|---|---|
| **管模型** | 租户模型注册、不可变版本、数据集、RBAC、审批及审计、统一 Control API | 真实 OIDC、强租户隔离、可信模型产物验真 |
| **训模型** | 动态训练任务、Argo/LLaMA-Factory、LoRA/QLoRA 配置、留出集评估及质量门禁 | 真 GPU 训练权重、独立测试、完整上线闭环 |
| **部署模型** | ModelDeployment Operator/CRD、vLLM、SGLang、TEI、llama.cpp、版本/灰度/回滚接口 | GPU 模型实际启动、真实加权流量、故障回滚 |
| **加速模型** | Benchmark、GPU 指标采集与 A/B 对照、量化/KV Cache/Batch 配置 | 同硬件同模型的 TTFT/TPOT、吞吐、显存、质量实测 |
| **运营模型** | Prometheus/Grafana、租户级 Operator 权限、API/控制台镜像、审计、恢复 Worker、备份校验 | SLO 告警、真实备份恢复、RPO/RTO、多节点 HA |

整体架构中，**PostgreSQL 保存管理元数据与用户期望状态**，**Kubernetes CRD 和 Argo 提供运行态事实**，**S3/MLflow 保存模型产物与版本**。UI 只调用 Control API，不应持有 Kubernetes 管理凭据。

## 代码结构

- `control-plane/`：FastAPI、SQL、迁移、租户权限、操作审计、任务恢复。
- `console/`：Next.js 产品管理控制台与 Playwright E2E。
- `operator/`：Go Kubernetes Operator、CRD、控制器。
- `charts/`：Helm、网关、推理引擎、训练及观测组件。
- `pipelines/`：训练后模型产物、留出集评估与质量门禁。
- `benchmarks/inference/`：对真实推理接口的 Benchmark 和 A/B 一致性检查。
- `ops/`：安全预检、CPU Kubernetes 测试、备份与恢复。
- `docs/`：平台架构、实施与验收、技术限制、来源说明。

## 本地启动（无需 GPU）

安装 Docker Compose，在项目根目录执行：

```bash
cp .env.compose.example .env
# 在 .env 中配置随机、唯一的 MODELOPS_PG_PASSWORD、MODELOPS_JWT_SECRET。
docker compose up --build -d postgres
docker compose run --rm --no-deps api alembic upgrade head
docker compose up --build -d api console
```

Console 默认 `http://localhost:3000`，API 默认 `http://127.0.0.1:8080`。本地开发模式没有接入 Kubernetes 时，**模型部署与训练接口会拒绝创建**，不会以 Mock 状态冒充部署成功。详见 [安装与环境说明](docs/LOCAL_AND_PRODUCTION_SETUP.md)。

### 无 GPU 自动化测试

```bash
cd control-plane
python -m pip install -e ".[dev]"
python -m pytest -q
cd ..
python -m unittest discover -s benchmarks/inference -p 'test_*.py' -v
```

GitHub Actions 还会运行 Go/Helm 契约测试、Web 控制台端到端测试、容器镜像构建和 CPU kind。最新新增的 `test_kind_runtime_e2e.py` 专门验证真实 **FastAPI → Kubernetes CRD → Operator → 扩缩/删除**，需要在 CI 准备实际 Kubernetes 环境。这不是 GPU 推理测试。

## 验收层级

| 级别 | 证据标准 |
|---|---|
| T0 源码 | 代码与上游出处可追溯 |
| T1 自动化 | 单测、静态校验、UI/API/Helm 契约 |
| T2 CPU Kubernetes | 真实命名空间、Operator 和服务组件运行 |
| T3 GPU Serving | 真机测量 TTFT、TPOT、吞吐、显存、延迟尾部 |
| T4 GPU Training | 真正产生权重、独立评测、模型发布与回滚 |
| T5 生产类集群 | 多节点容错、最小权限、恢复演练及 SLO |

**只有证据达到对应层级，才对外陈述相应成果。** 2026 年 10 月 11 日的 [旧平台审计](docs/PLATFORM_AUDIT_2026-10-11.md) 是当时快照，不包含后续所有控制面与前端提交，不能作为最新完成度。应以相应提交 SHA 的 [CI 记录](https://github.com/Benjamindaoson/ModelOps-Platform/actions) 和原始运行日志为准。

## 剩余重点

优先把无 GPU 的真实跨组件全链路和安全/恢复验收做完，然后用 RTX 3090 测试同权重 vLLM/SGLang、量化、KV Cache、批处理策略，保存原始请求/显存/延迟数据；再跑真实 LoRA/QLoRA 微调、独立留出集评估、质量审核、Canary 与回滚。多 GPU 和多节点 HA 是后续独立测试，不把它们混入单卡成绩。

相关文档：[跨组件验收计划](docs/INTEGRATION_ROADMAP_2026-10-12.md) · [训练任务生命周期](docs/TRAINING_JOB_LIFECYCLE.md) · [备份恢复](docs/BACKUP_RECOVERY_V2.md) · [推理测试](benchmarks/inference/README.md)。

## 开源来源与授权

本仓库基于 [GaeaRuiW/kube-llmops](https://github.com/GaeaRuiW/kube-llmops) 的 Apache-2.0 开源版本（固定来源提交 `74f8db47fa2690a4e71ae31532f36b35a587d266`）进行二次开发。上游 Operator、Helm 和观测体系是继承基础；新增 Control API、Console、恢复与证据校验等由 Git 历史区分。保留 [上游来源记录](docs/UPSTREAM_PROVENANCE.md)、[原上游 README](docs/upstream/README.md) 和 [LICENSE](LICENSE)。商用需单独审查各依赖许可证及安全配置。
