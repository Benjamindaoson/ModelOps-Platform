"""CPU loopback streaming proxy/exporter for an existing vLLM instance."""
import argparse
import asyncio
import json
import os
import subprocess
import time
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from ops.gpu_runtime_validation import validate_probe_url
from ops.observability.stream_metrics import StreamMeter


def create_app(upstream, version="unknown"):
    upstream = validate_probe_url(upstream)
    registry = CollectorRegistry()
    requests = Counter("modelops_inference_requests_total", "Completed inference requests", ["version","route","status"], registry=registry)
    errors = Counter("modelops_inference_errors_total", "Request/stream failures", ["version","reason"], registry=registry)
    latency = Histogram("modelops_inference_latency_seconds", "Complete response time", ["version"], buckets=(.05,.1,.2,.5,1,2,5,10,30,60,120), registry=registry)
    ttft = Histogram("modelops_inference_ttft_seconds", "First nonempty content time", ["version"], buckets=(.005,.01,.025,.05,.1,.2,.5,1,2,5,30), registry=registry)
    tokens = Counter("modelops_inference_output_tokens_total", "Actual completion usage tokens", ["version"], registry=registry)
    token_rate = Histogram("modelops_inference_tokens_per_second", "Actual tokens / full request wall time", ["version"], buckets=(1,10,25,50,100,200,500,1000,2000,5000), registry=registry)
    missing = Counter("modelops_inference_usage_missing_total", "Requests without observed final token usage", ["version"], registry=registry)
    inflight = Gauge("modelops_inference_inflight", "Active proxy inference streams", ["version"], registry=registry)
    gpu_util = Gauge("modelops_gpu_utilization_percent", "Whole GPU utilization", ["gpu"], registry=registry)
    gpu_memory = Gauge("modelops_gpu_memory_used_bytes", "Whole GPU used memory", ["gpu"], registry=registry)
    gpu_temp = Gauge("modelops_gpu_temperature_celsius", "GPU temperature", ["gpu"], registry=registry)
    gpu_available = Gauge("modelops_gpu_metrics_available", "NVML sampling availability; missing values never zero-filled", registry=registry)
    sample = {"at":0.0}

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=httpx.Timeout(120,connect=5), limits=httpx.Limits(max_connections=128,max_keepalive_connections=64)) as client:
            app.state.client = client
            yield

    app = FastAPI(title="ModelOps Serving Telemetry", lifespan=lifespan)
    app.state.registry = registry

    async def gpu_sample():
        if time.monotonic()-sample["at"] < 1: return
        sample["at"]=time.monotonic()
        def collect():
            try:
                p=subprocess.run(["nvidia-smi","--query-gpu=index,utilization.gpu,memory.used,temperature.gpu","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3)
                if p.returncode: return None
                return [line.split(",") for line in p.stdout.strip().splitlines()]
            except (OSError,subprocess.TimeoutExpired): return None
        rows=await asyncio.to_thread(collect)
        gpu_available.set(1 if rows else 0)
        if not rows:
            gpu_util.clear();gpu_memory.clear();gpu_temp.clear();return
        for row in rows:
            gpu=row[0].strip()
            for metric,text,factor in [(gpu_util,row[1],1),(gpu_memory,row[2],1048576),(gpu_temp,row[3],1)]:
                try: metric.labels(gpu).set(float(text)*factor)
                except ValueError: metric.labels(gpu).set(float("nan"))

    @app.get("/metrics")
    async def metrics():
        await gpu_sample()
        return Response(generate_latest(registry),media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    async def health():
        try:
            r=await app.state.client.get(upstream+"/health")
            return Response(r.content,status_code=r.status_code,media_type="application/json")
        except httpx.HTTPError: raise HTTPException(503,"Upstream unavailable")

    @app.get("/v1/models")
    async def models():
        try:
            r=await app.state.client.get(upstream+"/v1/models")
            return Response(r.content,status_code=r.status_code,media_type="application/json")
        except httpx.HTTPError: raise HTTPException(503,"Upstream unavailable")

    async def predict(request, route):
        if int(request.headers.get("content-length","0")) > 1024*1024: raise HTTPException(413,"Body too large")
        data=await request.body()
        if len(data)>1024*1024: raise HTTPException(413,"Body too large")
        try: body=json.loads(data)
        except ValueError: raise HTTPException(400,"Invalid JSON")
        if not isinstance(body,dict): raise HTTPException(400,"Object required")
        stream=body.get("stream") is True
        if stream:
            options=body.get("stream_options",{})
            if not isinstance(options,dict): raise HTTPException(400,"stream_options must be an object")
            body["stream_options"]={**options,"include_usage":True}
        began=time.perf_counter();inflight.labels(version).inc()
        try:
            req=app.state.client.build_request("POST",upstream+route,json=body)
            response=await app.state.client.send(req,stream=True)
        except httpx.HTTPError:
            inflight.labels(version).dec();errors.labels(version,"transport").inc();requests.labels(version,route,"error").inc()
            raise HTTPException(502,"Upstream transport failure")
        if response.status_code>=400:
            content=await response.aread();await response.aclose();inflight.labels(version).dec()
            errors.labels(version,"http").inc();requests.labels(version,route,"error").inc();latency.labels(version).observe(time.perf_counter()-began)
            return Response(content,status_code=response.status_code,media_type="application/json")
        if not stream:
            try:
                content=await response.aread()
                try:
                    payload=json.loads(content)
                    if not isinstance(payload,dict):raise ValueError("not object")
                except ValueError:
                    errors.labels(version,"invalid_upstream_json").inc();requests.labels(version,route,"error").inc()
                    latency.labels(version).observe(time.perf_counter()-began)
                    raise HTTPException(502,"Invalid upstream response")
                count=payload.get("usage",{}).get("completion_tokens")
                duration=time.perf_counter()-began
                if isinstance(count,int) and not isinstance(count,bool) and count>=0:
                    tokens.labels(version).inc(count);token_rate.labels(version).observe(count/max(duration,1e-9))
                else: missing.labels(version).inc()
                requests.labels(version,route,"ok").inc();latency.labels(version).observe(duration)
                return Response(content,status_code=response.status_code,media_type="application/json")
            finally:
                inflight.labels(version).dec();await response.aclose()
        meter=StreamMeter(start=began)
        async def relay():
            cancelled=False
            try:
                async for chunk in response.aiter_bytes():
                    meter.feed(chunk,now=time.perf_counter())
                    yield chunk
            except asyncio.CancelledError:
                cancelled=True;raise
            except httpx.HTTPError:
                meter.error="transport"
                raise
            finally:
                duration=time.perf_counter()-began
                reason=meter.error or ("client_disconnect" if cancelled else ("truncated_stream" if not meter.done else None))
                if reason: errors.labels(version,reason).inc()
                requests.labels(version,route,"error" if reason else "ok").inc()
                latency.labels(version).observe(duration)
                if meter.first_token_s is not None: ttft.labels(version).observe(meter.first_token_s)
                if meter.output_tokens is not None:
                    tokens.labels(version).inc(meter.output_tokens);token_rate.labels(version).observe(meter.output_tokens/max(duration,1e-9))
                else: missing.labels(version).inc()
                inflight.labels(version).dec();await response.aclose()
        return StreamingResponse(relay(),media_type="text/event-stream",headers={"Cache-Control":"no-cache"})

    @app.post("/v1/completions")
    async def completions(request:Request): return await predict(request,"/v1/completions")
    @app.post("/v1/chat/completions")
    async def chat(request:Request): return await predict(request,"/v1/chat/completions")
    return app


def main():
    import uvicorn
    p=argparse.ArgumentParser();p.add_argument("--upstream",required=True);p.add_argument("--port",type=int,default=19780);p.add_argument("--version",default="unknown")
    a=p.parse_args()
    uvicorn.run(create_app(a.upstream,a.version),host="127.0.0.1",port=a.port,access_log=False)


if __name__=="__main__":main()
