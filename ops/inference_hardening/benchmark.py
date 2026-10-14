"""One genuine OpenAI SSE measurement client for both engines; raw requests persisted."""
import asyncio,json,statistics,subprocess,threading,time,hashlib
from pathlib import Path
import httpx
from ops.observability.stream_metrics import StreamMeter
from .contracts import digest,trial_valid
from .runtime import E,ROOT

def percentile(values,q):
    if not values:return None
    values=sorted(values);at=(len(values)-1)*q;lo=int(at);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(at-lo)

async def request(client,url,name,prompt,outtokens,seed,sem,record):
    async with sem:
        start=time.perf_counter();meter=StreamMeter(start)
        payload={"model":name,"prompt":prompt,"max_tokens":outtokens,"temperature":0,"seed":seed,"ignore_eos":True,
                 "stream":True,"stream_options":{"include_usage":True}}
        row={"request_id":record,"input_sha256":hashlib.sha256(json.dumps(prompt).encode()).hexdigest(),"seed":seed}
        try:
            async with client.stream("POST",url+"/v1/completions",json=payload,timeout=180) as r:
                r.raise_for_status()
                async for chunk in r.aiter_bytes():meter.feed(chunk,time.perf_counter())
            elapsed=time.perf_counter()-start
            if meter.error or not meter.done:raise ValueError(meter.error or "stream_interrupted")
            if meter.output_tokens!=outtokens or meter.prompt_tokens!=len(prompt):raise ValueError("actual_token_budget_mismatch")
            if meter.first_token_s is None:raise ValueError("first_content_missing")
            row.update(success=True,input_tokens=meter.prompt_tokens,output_tokens=meter.output_tokens,
                       ttft_ms=meter.first_token_s*1000,e2e_ms=elapsed*1000,
                       tpot_ms=(elapsed-meter.first_token_s)*1000/max(1,meter.output_tokens-1),
                       chunk_interarrival_ms=[(b-a)*1000 for a,b in zip(meter.content_times,meter.content_times[1:])],
                       content_events=len(meter.content_times),text=meter.text)
        except Exception as ex:row.update(success=False,error=type(ex).__name__+": "+str(ex),e2e_ms=(time.perf_counter()-start)*1000)
        return row

def gpu_poll(stop,rows):
    while not stop.is_set():
        try:
            r=subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,power.draw","--format=csv,noheader,nounits"],
                             capture_output=True,text=True,timeout=5)
            v=[float(x.strip()) for x in r.stdout.splitlines()[0].split(",")]
            rows.append({"time":time.time(),"util_percent":v[0],"used_mib":v[1],"power_w":v[2]})
        except Exception:pass
        stop.wait(.5)

async def measure(server,prompts,output_tokens,concurrency,seed,folder,protocol_sha,source_sha,warmups=3):
    folder.mkdir(parents=True,exist_ok=True);raw=folder/"requests.jsonl"
    sem=asyncio.Semaphore(concurrency)
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=128,max_keepalive_connections=64)) as client:
        warm=[]
        for i in range(warmups):warm.append(await request(client,server.url,server.config["name"],prompts[i],output_tokens,seed,sem,-i-1))
        (folder/"warmup.json").write_text(json.dumps(warm,indent=2))
        if not all(x["success"] for x in warm):raise RuntimeError("Genuine warmup/token validation failed; inspect "+str(folder))
        gpu=[];stop=threading.Event();thread=threading.Thread(target=gpu_poll,args=(stop,gpu),daemon=True);thread.start()
        start=time.perf_counter();rows=[]
        with raw.open("w") as log:
            tasks=[asyncio.create_task(request(client,server.url,server.config["name"],p,output_tokens,seed+i,sem,i)) for i,p in enumerate(prompts)]
            for completed in asyncio.as_completed(tasks):
                row=await completed;rows.append(row);log.write(json.dumps(row)+"\n");log.flush()
        wall=time.perf_counter()-start;stop.set();thread.join(8)
    (folder/"gpu.json").write_text(json.dumps(gpu,indent=2))
    good=[r for r in rows if r["success"]];errors=len(rows)-len(good)
    metrics={key:{f"p{int(q*100)}":percentile([r[key] for r in good],q) for q in (.5,.95,.99)} for key in ["ttft_ms","tpot_ms","e2e_ms"]}
    result={"status":"PASS" if not errors else "FAIL","requests":len(rows),"errors":errors,"error_rate":errors/len(rows),"wall_s":wall,
            "input_tokens":sum(r.get("input_tokens",0) for r in good),"output_tokens":sum(r.get("output_tokens",0) for r in good),
            "expected_input_tokens":len(prompts[0]),"expected_output_tokens":output_tokens,
            "requests_s":len(good)/wall,"input_tokens_s":sum(r.get("input_tokens",0) for r in good)/wall,
            "output_tokens_s":sum(r.get("output_tokens",0) for r in good)/wall,"latency":metrics,
            "gpu_samples":len(gpu),"gpu":{"peak_used_mib":max([r["used_mib"] for r in gpu],default=None),
                                         "mean_util_percent":statistics.mean([r["util_percent"] for r in gpu]) if gpu else None,
                                         "peak_util_percent":max([r["util_percent"] for r in gpu],default=None),
                                         "mean_power_w":statistics.mean([r["power_w"] for r in gpu]) if gpu else None},
            "itl_scope":"Content-chunk arrival gaps, not claimed per-token when chunks combine tokens",
            "server_load_s":server.load_s,"config":server.config,"raw_sha":digest(raw),"gpu_sha":digest(folder/"gpu.json"),
            "source_sha":source_sha,"protocol_sha":protocol_sha}
    if not trial_valid(result):result["status"]="FAIL"
    (folder/"receipt.json").write_text(json.dumps(result,indent=2)+"\n")
    return result
