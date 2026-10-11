"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { Activity, ArrowDownUp, Check, CheckCircle2, CloudOff, Clock3,
  Database, HardDriveDownload, Layers3, Plus, RefreshCcw, Server, ShieldAlert,
  Terminal, Trash2, X } from "lucide-react";
import { ApiError, apiRequest, fmtDate, shortId } from "@/lib/api";
import type { Artifact, AuditEvent, Dataset, Deployment, Evaluation, Overview, TrainJob } from "@/lib/api";

const TITLES: Record<string, [string, string]> = {
  dashboard: ["Workspace overview", "A verifiable view of your model infrastructure and runtime state."],
  models: ["Model registry", "Immutable model identities, source revisions and artifact provenance."],
  deployments: ["Model deployments", "Desired state in Kubernetes, with live observed state where connected."],
  datasets: ["Dataset registry", "Versioned datasets, immutable checksums and heldout coverage."],
  training: ["Fine-tuning jobs", "Submit independent, parameterized Argo workflows and inspect real status."],
  evaluations: ["Evaluation evidence", "Signed benchmark records and independently approved quality results."],
  audit: ["Audit trail", "Traceable, tenant-scoped changes to model and infrastructure resources."],
  settings: ["Environment", "Security, API mode and runtime connection prerequisites."],
};

const SOURCES: Record<string, string> = {
  dashboard: "overview", models: "models", deployments: "deployments",
  datasets: "datasets", training: "train-jobs", evaluations: "evaluations",
  audit: "audit", settings: "overview",
};

function Status({ children, tone = "neutral" }: { children: React.ReactNode; tone?: "good" | "warning" | "neutral" }) {
  return <span className={"status " + tone}><span className="status-dot"/>{children}</span>;
}

function ShortHash({ value }: { value: string }) {
  return <code className="short-hash" title={value}>{shortId(value)}</code>;
}

function Empty({ message }: { message: string }) {
  return <div className="empty-state"><div className="empty-icon"><CloudOff size={24}/></div>
    <strong>Nothing to display</strong><p>{message}</p></div>;
}

function FormFields({ submit, onCancel, busy, children, title }: {
  submit: (e: FormEvent<HTMLFormElement>) => void; onCancel: () => void;
  busy: boolean; children: React.ReactNode; title: string;
}) {
  return <div className="form-panel"><div className="form-heading"><strong>{title}</strong>
    <button type="button" className="icon-button" onClick={onCancel} aria-label="Close form"><X size={18}/></button></div>
    <form onSubmit={submit} className="create-form">{children}
      <div className="form-actions"><button type="button" className="secondary-button" onClick={onCancel}>Cancel</button>
        <button className="primary-button" type="submit" disabled={busy}>{busy ? "Submitting…" : "Submit"}</button>
      </div>
    </form>
  </div>;
}

function Field({ label, name, placeholder, required = true, type = "text", defaultValue, min, step }: {
  label: string; name: string; placeholder?: string; required?: boolean; type?: string;
  defaultValue?: string | number; min?: string | number; step?: string;
}) {
  return <label className="field">{label}
    <input name={name} placeholder={placeholder} required={required} type={type}
      defaultValue={defaultValue} min={min} step={step} autoComplete="off"/>
  </label>;
}

function SelectField({ label, name, choices, defaultValue }: {
  label: string; name: string; choices: { value: string; text: string }[]; defaultValue?: string;
}) {
  return <label className="field">{label}<select name={name} required defaultValue={defaultValue || choices[0]?.value || ""}>
    {choices.map(c => <option key={c.value} value={c.value}>{c.text}</option>)}
  </select></label>;
}

function Models({ rows }: { rows: Artifact[] }) {
  if (!rows.length) return <Empty message="Register a versioned model to begin. Artifact digests remain unverified until a trusted worker checks the bytes."/>;
  return <div className="table-scroll"><table><thead><tr><th>MODEL / VERSION</th><th>FAMILY</th><th>UPSTREAM SOURCE</th><th>PROVENANCE</th><th>CREATED</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.id}>
      <td><strong>{r.name}</strong><span className="sub-line">v{r.version} · <ShortHash value={r.id}/></span></td>
      <td><Status>{r.family.toUpperCase()}</Status></td>
      <td><span className="code-cell" title={r.source}>{r.source}</span><span className="sub-line">Revision <ShortHash value={r.revision}/></span></td>
      <td><Status tone={r.digest_verified ? "good" : "warning"}>{r.digest_verified ? "VERIFIED" : "DECLARED"}</Status><span className="sub-line"><ShortHash value={r.digest}/></span></td>
      <td>{fmtDate(r.created_at)}</td>
    </tr>)}</tbody></table></div>;
}

function Datasets({ rows }: { rows: Dataset[] }) {
  if (!rows.length) return <Empty message="Register a real dataset location and an immutable manifest checksum. Train/heldout separation is required."/>;
  return <div className="table-scroll"><table><thead><tr><th>DATASET / VERSION</th><th>STORAGE URI</th><th>RECORDS</th><th>MANIFEST HASH</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.id}><td><strong>{r.name}</strong><span className="sub-line">Version {r.version}</span></td>
      <td><span className="code-cell" title={r.uri}>{r.uri}</span></td>
      <td>{r.train_count.toLocaleString()} train<span className="sub-line">{r.heldout_count.toLocaleString()} heldout</span></td>
      <td><ShortHash value={r.digest}/><span className="sub-line">{fmtDate(r.created_at)}</span></td></tr>)}</tbody></table></div>;
}

function Deployments({ rows, act, busy }: {
  rows: Deployment[]; act: (path: string, body: unknown, method?: "POST" | "PATCH" | "DELETE") => Promise<void>; busy: boolean;
}) {
  if (!rows.length) return <Empty message="No deployments have been submitted to Kubernetes. Offline metadata-only mode cannot create fake runtime instances."/>;
  return <div className="table-scroll"><table><thead><tr><th>DEPLOYMENT</th><th>ENGINE</th><th>RUNTIME PHASE</th><th>RESOURCES</th><th>ACTIONS</th></tr></thead>
    <tbody>{rows.map(r => <tr key={r.id}><td><strong>{r.name}</strong><span className="sub-line">Generation {r.generation} · <ShortHash value={r.artifact_id}/></span></td>
      <td>{r.engine}</td>
      <td><Status tone={r.runtime_verified && r.observed_phase === "Ready" ? "good" : "warning"}>
        {r.observed_phase || "Pending"}</Status><span className="sub-line">{r.intent}</span></td>
      <td>{r.replicas} replicas<span className="sub-line">{r.gpu} GPU each</span></td>
      <td><div className="row-actions">
        <button disabled={busy || r.intent === "deleted"} className="table-button"
          onClick={() => act("deployments/" + r.id + "/scale",
            { replicas: r.replicas + 1, expected_generation: r.generation }, "PATCH")}>Scale +</button>
        <button disabled={busy || r.replicas === 0 || r.intent === "deleted"} className="table-button"
          onClick={() => act("deployments/" + r.id + "/scale",
            { replicas: Math.max(0, r.replicas - 1), expected_generation: r.generation }, "PATCH")}>Scale −</button>
        <button disabled={busy || r.intent === "deleted"} className="table-button danger"
          onClick={() => { if (window.confirm("Delete Kubernetes deployment " + r.name + "?")) {
            void act("deployments/" + r.id, undefined, "DELETE");
          } }}><Trash2 size={14}/></button>
      </div></td>
    </tr>)}</tbody></table></div>;
}

function Jobs({ rows }: { rows: TrainJob[] }) {
  if (!rows.length) return <Empty message="No training jobs. Submissions require a real Kubernetes cluster and an Argo workflow template."/>;
  return <div className="table-scroll"><table><thead><tr><th>TRAINING JOB</th><th>METHOD</th><th>MODEL / DATASET</th><th>ARGO STATE</th></tr></thead>
  <tbody>{rows.map(j => <tr key={j.id}><td><strong>{j.name}</strong><span className="sub-line"><ShortHash value={j.id}/></span></td>
    <td><Status>{j.method.toUpperCase()}</Status></td><td>Model <ShortHash value={j.artifact_id}/><span className="sub-line">Data <ShortHash value={j.dataset_id}/></span></td>
    <td><Status tone={j.observed_phase === "Succeeded" ? "good" : "warning"}>{j.observed_phase}</Status></td>
  </tr>)}</tbody></table></div>;
}

function Evaluations({ rows }: { rows: Evaluation[] }) {
  if (!rows.length) return <Empty message="No trusted evaluation reports. Only an authenticated training worker can submit signed heldout evidence."/>;
  return <div className="table-scroll"><table><thead><tr><th>EVIDENCE</th><th>MODEL</th><th>QUALITY GATE</th><th>METRICS</th></tr></thead>
  <tbody>{rows.map(e => <tr key={e.id}><td><ShortHash value={e.id}/></td><td><ShortHash value={e.artifact_id}/></td>
    <td><Status tone={e.verified && e.passed ? "good" : "warning"}>{e.verified && e.passed ? "PASS" : "NOT APPROVED"}</Status></td>
    <td>{Object.entries(e.metrics).slice(0,3).map(([k,v]) =>
      <div key={k} className="metric-line">{k}: {Number(v).toFixed(3)}</div>)}</td>
  </tr>)}</tbody></table></div>;
}

function Audit({ rows }: { rows: AuditEvent[] }) {
  if (!rows.length) return <Empty message="Changes to models, datasets, training and deployments will appear here."/>;
  return <div className="table-scroll"><table><thead><tr><th>EVENT</th><th>ACTOR</th><th>RESOURCE</th><th>TIME</th></tr></thead>
  <tbody>{rows.map(e => <tr key={e.id}><td><strong>{e.action}</strong></td><td>{e.actor}</td>
    <td>{e.object_kind}<span className="sub-line"><ShortHash value={e.object_id}/></span></td>
    <td>{fmtDate(e.at)}</td></tr>)}</tbody></table></div>;
}

function Dashboard({ overview }: { overview: Overview }) {
  const metrics = [
    { title: "Model artifacts", count: overview.models, icon: HardDriveDownload },
    { title: "Datasets", count: overview.datasets, icon: Database },
    { title: "Deployments", count: overview.deployments, icon: Server },
    { title: "Training jobs", count: overview.training_jobs, icon: Layers3 },
  ];
  return <>
    <div className="metric-grid">{metrics.map(m => { const Icon = m.icon; return <div className="metric-card" key={m.title}>
      <div className="metric-card-top"><span>{m.title}</span><Icon size={18}/></div>
      <strong>{m.count.toLocaleString()}</strong><span className="metric-note">Metadata records · tenant scoped</span>
    </div>; })}</div>
    <div className="dashboard-grid">
      <div className="panel"><div className="panel-heading"><h2>Infrastructure status</h2><Activity size={18}/></div>
        <div className="health-row"><span>Kubernetes control plane</span>
          <Status tone={overview.runtime_connected ? "good" : "warning"}>
            {overview.runtime_connected ? "CONNECTED" : "DISCONNECTED"}</Status></div>
        <div className="health-row"><span>Runtime model verification</span><Status tone="warning">NOT VERIFIED</Status></div>
        <div className="health-row"><span>Data plane availability SLO</span><Status tone="warning">NO LIVE MEASUREMENTS</Status></div>
        <p className="panel-footnote">No model throughput or availability claim is inferred from successful metadata writes.</p>
      </div>
      <div className="panel"><div className="panel-heading"><h2>Delivery and quality gates</h2><CheckCircle2 size={18}/></div>
        <div className="check-row"><Check size={16}/> Immutable model and dataset versions</div>
        <div className="check-row"><Check size={16}/> Independent evaluation before approval</div>
        <div className="check-row"><Check size={16}/> Tenant RBAC and audit events</div>
        <div className="check-row pending"><Clock3 size={16}/> GPU, HA and production evidence pending</div>
        <p className="panel-footnote">The Kubernetes Operator—not this metadata API—determines workload readiness.</p>
      </div>
    </div>
  </>;
}

function NewRecord({ section, artifacts, datasets, close, execute, busy }: {
  section: string; artifacts: Artifact[]; datasets: Dataset[]; close: () => void;
  execute: (path: string, data: unknown) => Promise<void>; busy: boolean;
}) {
  const [busyForm, setBusyForm] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget);
    const text = (name: string) => String(f.get(name) || "").trim();
    const num = (name: string) => Number(text(name));
    let payload: Record<string, unknown> = {};
    let resource = section;
    if (section === "models") {
      payload = { name: text("name"), version: num("version"), family: text("family"),
        source: text("source"), revision: text("revision"), digest: text("digest") };
    } else if (section === "datasets") {
      payload = { name: text("name"), version: num("version"), uri: text("uri"),
        digest: text("digest"), train_count: num("train_count"), heldout_count: num("heldout_count") };
    } else if (section === "deployments") {
      payload = { name: text("name"), artifact_id: text("artifact_id"),
        engine: text("engine"), replicas: num("replicas"), gpu: num("gpu") };
    } else if (section === "training") {
      resource = "train-jobs";
      payload = { name: text("name"), artifact_id: text("artifact_id"),
        dataset_id: text("dataset_id"), method: text("method"),
        output_name: text("output_name"), epochs: num("epochs"), batch_size: num("batch_size"),
        lr: num("lr"), lora_rank: num("lora_rank"), lora_alpha: num("lora_alpha"),
        gradient_accumulation_steps: num("gradient_accumulation_steps"),
        gpu: num("gpu"), min_token_f1: num("min_token_f1") };
    }
    setBusyForm(true);
    try { await execute(resource, payload); close(); } finally { setBusyForm(false); }
  }
  const disabled = busy || busyForm;
  return <FormFields title={
    section === "models" ? "Register a model version" :
    section === "datasets" ? "Register a dataset version" :
    section === "training" ? "Submit Argo training job" : "Create Kubernetes deployment"}
    submit={submit} onCancel={close} busy={disabled}>
    {section === "models" && <>
      <div className="form-grid"><Field label="Model name" name="name" placeholder="qwen-coder"/>
        <Field label="Version" name="version" type="number" min={1} defaultValue={1}/>
        <SelectField label="Model family" name="family" choices={["llm","embedding","asr","tts"].map(x=>({value:x,text:x.toUpperCase()}))}/>
        <Field label="HF revision / git SHA" name="revision" placeholder="Immutable upstream commit hash"/></div>
      <Field label="Hugging Face repository / artifact source" name="source" placeholder="Qwen/Qwen2.5-0.5B-Instruct"/>
      <Field label="SHA-256 digest (64 hexadecimal characters)" name="digest" placeholder="Actual artifact digest, verified externally"/>
      <p className="form-hint">Registration preserves your declared hash. Runtime verification is separate; this does not attest to artifact bytes.</p>
    </>}
    {section === "datasets" && <>
      <div className="form-grid"><Field label="Dataset name" name="name" placeholder="customer-support-v1"/>
        <Field label="Version" name="version" type="number" min={1} defaultValue={1}/></div>
      <Field label="S3 or HF dataset URI" name="uri" placeholder="s3://datasets/customer-support/v1/"/>
      <Field label="Dataset manifest SHA-256" name="digest" placeholder="64 hexadecimal characters"/>
      <div className="form-grid"><Field label="Training examples" name="train_count" type="number" min={1}/>
        <Field label="Heldout examples (minimum 20)" name="heldout_count" type="number" min={20}/></div>
    </>}
    {section === "deployments" && <>
      <Field label="Deployment name" name="name" placeholder="qwen-chat-prod"/>
      <SelectField label="Artifact version" name="artifact_id" choices={artifacts.length ?
        artifacts.map(a=>({value:a.id,text:a.name+" · v"+a.version+" · "+a.family})) :
        [{value:"",text:"Register a model first"}]}/>
      <div className="form-grid"><SelectField label="Engine" name="engine"
        choices={["vllm","sglang","tei","llamacpp"].map(x=>({value:x,text:x}))}/>
        <Field label="Replicas" name="replicas" type="number" min={0} defaultValue={1}/>
        <Field label="GPU per replica" name="gpu" type="number" min={0} defaultValue={1}/></div>
      <p className="form-hint">Creates an actual Kubernetes ModelDeployment CRD; requests are blocked when no cluster is connected.</p>
    </>}
    {section === "training" && <>
      <div className="form-grid"><Field label="Job name" name="name" placeholder="qwen-domain-lora"/>
        <Field label="Output model name" name="output_name" placeholder="qwen-support-v2"/></div>
      <SelectField label="Base model" name="artifact_id" choices={artifacts.filter(a=>a.family==="llm").length ?
        artifacts.filter(a=>a.family==="llm").map(a=>({value:a.id,text:a.name+" v"+a.version})) :
        [{value:"",text:"Register an LLM first"}]}/>
      <SelectField label="Dataset" name="dataset_id" choices={datasets.length ?
        datasets.map(d=>({value:d.id,text:d.name+" v"+d.version})) :
        [{value:"",text:"Register a dataset first"}]}/>
      <div className="form-grid">
        <SelectField label="Method" name="method" choices={["lora","qlora","full"].map(x=>({value:x,text:x.toUpperCase()}))}/>
        <Field label="Epochs" name="epochs" type="number" min={1} defaultValue={3}/>
        <Field label="Batch size" name="batch_size" type="number" min={1} defaultValue={1}/>
        <Field label="Learning rate" name="lr" type="number" min="0.0000001" step="any" defaultValue={0.0002}/>
        <Field label="LoRA rank" name="lora_rank" type="number" min={1} defaultValue={8}/>
        <Field label="LoRA alpha" name="lora_alpha" type="number" min={1} defaultValue={16}/>
        <Field label="Gradient accumulation" name="gradient_accumulation_steps" type="number" min={1} defaultValue={4}/>
        <Field label="GPU count" name="gpu" type="number" min={0} defaultValue={1}/>
        <Field label="Min. token F1" name="min_token_f1" type="number" step="0.01" min={0} defaultValue={0.55}/>
      </div>
      <p className="form-hint">Requires the real parameterized Argo template and tenant namespace. No offline jobs are marked successful.</p>
    </>}
  </FormFields>;
}

export default function Workspace({ section }: { section: string }) {
  const [data, setData] = useState<unknown>(null);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [writing, setWriting] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const refresh = useCallback(() => { setReloadKey(x=>x+1); }, []);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(""); setNotice("");
    Promise.all([
      apiRequest<unknown>(SOURCES[section] || "overview"),
      apiRequest<Artifact[]>("models").catch(() => [] as Artifact[]),
      apiRequest<Dataset[]>("datasets").catch(() => [] as Dataset[]),
    ]).then(([primary, models, registeredDatasets]) => {
      if (!active) return;
      setData(primary); setArtifacts(models); setDatasets(registeredDatasets);
    }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to load"); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active=false; };
  }, [section, reloadKey]);

  async function act(path: string, body: unknown, method: "POST" | "PATCH" | "DELETE" = "POST") {
    setWriting(true); setNotice(""); setError("");
    try {
      await apiRequest(path, body, method);
      setNotice("Request submitted to the control API. Runtime readiness must be verified separately.");
      refresh();
    } catch (err) {
      const prefix = err instanceof ApiError && err.status === 503 ? "Runtime not connected: " : "";
      setError(prefix + (err instanceof Error ? err.message : "Operation failed"));
      // Propagate so forms remain open when a request fails.
      throw err;
    } finally { setWriting(false); }
  }

  const meta = TITLES[section] || TITLES.dashboard;
  const creatable = ["models","datasets","deployments","training"].includes(section);
  return <>
    <div className="page-heading"><div><div className="eyebrow">MODEL OPERATIONS / {section.toUpperCase()}</div>
      <h1>{meta[0]}</h1><p>{meta[1]}</p></div>
      <div className="heading-actions"><button className="secondary-button" onClick={refresh}><RefreshCcw size={16}/> Refresh</button>
        {creatable && <button className="primary-button" onClick={()=>setFormOpen(x=>!x)}><Plus size={17}/>
          {section==="models"?"Register model":section==="datasets"?"Add dataset":section==="training"?"New training job":"New deployment"}
        </button>}</div>
    </div>
    {error && <div className="message error" role="alert"><ShieldAlert size={18}/><span>{error}</span><button className="icon-button" onClick={()=>setError("")}><X size={16}/></button></div>}
    {notice && <div className="message success"><CheckCircle2 size={18}/>{notice}</div>}
    {formOpen && <NewRecord section={section} artifacts={artifacts} datasets={datasets}
      close={()=>setFormOpen(false)} busy={writing} execute={async (path,body)=>act(path,body)}/>}
    {loading ? <div className="loading-table"><div className="loading-spinner"/> Fetching live control-plane records…</div> :
      section==="dashboard" || section==="settings" ?
        (section==="dashboard" ? <Dashboard overview={data as Overview}/> :
          <div className="dashboard-grid"><div className="panel">
            <div className="panel-heading"><h2>Environment connection</h2><Terminal size={18}/></div>
            <div className="health-row"><span>Kubernetes runtime</span><Status tone={(data as Overview)?.runtime_connected ? "good" : "warning"}>{(data as Overview)?.runtime_connected ? "CONNECTED" : "DISCONNECTED"}</Status></div>
            <p className="panel-footnote">Tenants are separated by identity claims and Kubernetes namespaces. Production access requires OIDC, PostgreSQL, cluster policies and verified credentials.</p>
          </div><div className="panel"><div className="panel-heading"><h2>Verification boundary</h2><ShieldAlert size={18}/></div>
          <p>Model and dataset registration is metadata only. Launching models, serving requests, using GPUs, and training models require actual Kubernetes runtime evidence. This UI never displays a synthetic success as a real deployment.</p>
        </div></div>) :
      <div className="panel table-panel">
        <div className="panel-heading"><div><h2>{meta[0]}</h2>
          <span className="panel-subtitle">{Array.isArray(data) ? data.length : 0} records · tenant scoped</span></div>
          <ArrowDownUp size={18}/>
        </div>
        {section==="models" && <Models rows={(data as Artifact[]) || []}/>}
        {section==="datasets" && <Datasets rows={(data as Dataset[]) || []}/>}
        {section==="deployments" && <Deployments rows={(data as Deployment[]) || []} act={act} busy={writing}/>}
        {section==="training" && <Jobs rows={(data as TrainJob[]) || []}/>}
        {section==="evaluations" && <Evaluations rows={(data as Evaluation[]) || []}/>}
        {section==="audit" && <Audit rows={(data as AuditEvent[]) || []}/>}
      </div>
    }
    <footer className="page-foot">ModelOps Platform · Engineering Preview · Measured evidence only</footer>
  </>;
}
