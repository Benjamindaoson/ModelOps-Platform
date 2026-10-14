"""Own only this experiment's process groups; API identity checked before use."""
import json,os,signal,socket,subprocess,time
from pathlib import Path
import httpx,psutil
from ops.run_model_comparison import stop_owned
from .contracts import digest

ROOT=Path(__file__).resolve().parents[2]
E=ROOT/"Evidence/inference-hardening"

def wait_port_release(port,timeout=15):
    deadline=time.monotonic()+timeout
    while True:
        with socket.socket() as probe:
            probe.settimeout(.2)
            occupied=probe.connect_ex(("127.0.0.1",port))==0
        if not occupied:return
        if time.monotonic()>=deadline:raise RuntimeError("Loopback port is still occupied; no unknown process was adopted or stopped")
        time.sleep(.1)

class Server:
    def __init__(self,config):
        self.config=config;self.p=None;self.owned=None;self.load_s=None
        self.url="http://127.0.0.1:"+str(config.get("port",19801))
    def __enter__(self):
        E.mkdir(exist_ok=True);port=self.config.get("port",19801)
        wait_port_release(port)
        with socket.socket() as s:
            s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(("127.0.0.1",port))
        ident=self.config["label"];folder=E/"servers"/ident;folder.mkdir(parents=True,exist_ok=True)
        config=folder/"config.json";config.write_text(json.dumps(self.config,indent=2)+"\n")
        env={k:v for k,v in os.environ.items() if not any(x in k.upper() for x in ("TOKEN","PASSWORD","SECRET","API_KEY","PRIVATE_KEY"))}
        env.update(PYTHONPATH=str(ROOT),HF_HUB_OFFLINE="1",TOKENIZERS_PARALLELISM="false",XDG_CACHE_HOME=str(ROOT/".tools/hardening-cache"),
                   VLLM_CACHE_ROOT=str(ROOT/".tools/hardening-cache/vllm"))
        cache=ROOT/".tools/hardening-cache"
        for key,name in [("TRITON_CACHE_DIR","triton"),("TORCHINDUCTOR_CACHE_DIR","inductor"),("HF_HOME","hf"),("TMPDIR","tmp")]:
            path=cache/name;path.mkdir(parents=True,exist_ok=True);env[key]=str(path)
        env.pop("LD_LIBRARY_PATH",None)
        env["TORCH_EXTENSIONS_DIR"]=str(ROOT/".tools/hardening-cache/torch");env["MAX_JOBS"]="2"
        if self.config.get("profile"):env["VLLM_TORCH_PROFILER_DIR"]=str(E/"profiling"/ident)
        py=ROOT/(".gpu-venv" if self.config["engine"]=="vllm" else ".sglang-venv")/"bin/python"
        env["PATH"]=str(py.parent)+os.pathsep+env.get("PATH","")
        self.log=(folder/"server.log").open("ab")
        self.p=subprocess.Popen([str(py),"-m","ops.locked_exec","--",str(py),"-m","ops.inference_hardening.backend","--config",str(config)],
                                cwd=ROOT,env=env,stdout=self.log,stderr=subprocess.STDOUT,start_new_session=True)
        self.owned={"pid":self.p.pid,"create_time":psutil.Process(self.p.pid).create_time()}
        (folder/"process.json").write_text(json.dumps(self.owned))
        start=time.perf_counter()
        try:
            while time.perf_counter()-start<480:
                if self.p.poll() is not None:raise RuntimeError("Model server exited; inspect "+str(folder/"server.log"))
                try:
                    r=httpx.get(self.url+"/v1/models",timeout=3)
                    if r.status_code==200 and self.config["name"] in [x["id"] for x in r.json()["data"]]:
                        self.load_s=time.perf_counter()-start;return self
                except (httpx.HTTPError,ValueError,KeyError):pass
                time.sleep(1)
            raise RuntimeError("Real model readiness timeout")
        except BaseException:
            self.__exit__(None,None,None);raise
    def __exit__(self,*exc):
        if self.p:stop_owned(self.p,self.owned,"ops.inference_hardening.backend")
        if hasattr(self,"log"):self.log.close()
        if self.p:wait_port_release(self.config.get("port",19801))
