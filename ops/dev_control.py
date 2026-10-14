"""Ephemeral loopback development control plane. Never suitable for production auth."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import os,secrets,socket,threading,time,sys
import httpx,jwt,uvicorn

def owned_evidence_root(root,subdir=None):
    root=Path(root).resolve(); path=(root/(subdir or "Evidence/v1")).resolve()
    if not path.is_relative_to(root):raise ValueError("Evidence escaped project root")
    return path

@contextmanager
def control_session(root: Path,subject="v1-runtime-validation",evidence_subdir=None):
    evidence=owned_evidence_root(root,evidence_subdir);evidence.mkdir(parents=True,exist_ok=True)
    secret=secrets.token_urlsafe(48)
    previous={k:os.environ.get(k) for k in ["MODELOPS_AUTH_MODE","MODELOPS_ENV","MODELOPS_RUNTIME",
        "MODELOPS_JWT_SECRET","MODELOPS_DATABASE_URL"]}
    os.environ.update(MODELOPS_AUTH_MODE="dev",MODELOPS_ENV="development",MODELOPS_RUNTIME="disabled",
        MODELOPS_JWT_SECRET=secret,MODELOPS_DATABASE_URL="sqlite:///"+str(evidence/"modelops.sqlite"))
    sys.path.insert(0,str(root/"control-plane"))
    from modelops.config import Settings
    from modelops.main import create_app
    app=create_app(Settings(database_url=os.environ["MODELOPS_DATABASE_URL"],runtime="linux",
        environment="development",auth_mode="dev",jwt_secret=secret,
        artifact_root=str(evidence/"runtime"),gpu_python=str(root/".gpu-venv/bin/python")))
    with socket.socket() as s:s.bind(("127.0.0.1",0));port=s.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=port,log_level="warning",access_log=False))
    thread=threading.Thread(target=server.run,daemon=True);thread.start()
    now=datetime.now(timezone.utc)
    token=jwt.encode({"iss":"modelops-local","aud":"modelops-dev","sub":subject,"tenant":"lab","role":"admin",
        "iat":now,"exp":now+timedelta(hours=1)},secret,algorithm="HS256")
    client=httpx.Client(base_url=f"http://127.0.0.1:{port}",headers={"Authorization":"Bearer "+token},timeout=60)
    try:
        for _ in range(100):
            try:
                if client.get("/healthz").status_code==200:break
            except httpx.HTTPError:pass
            time.sleep(.1)
        yield client
    finally:
        client.close();server.should_exit=True;thread.join(10)
        for k,value in previous.items():
            if value is None:os.environ.pop(k,None)
            else:os.environ[k]=value
