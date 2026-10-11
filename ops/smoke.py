#!/usr/bin/env python3
"""Real HTTP smoke checks for the OpenAI-compatible serving fleet.

Default policy: fail closed if any requested model family fails.
Only writes transport measurements and response shapes; no prompts/audio,
model outputs, auth headers, or credentials are persisted.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class SmokeFailure(ValueError):
    pass


MODALITIES = ("chat", "embedding", "transcription", "speech")


def check_origin(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.netloc or p.username or p.password or p.query or p.fragment or p.path not in ("","/"):
        raise SmokeFailure("endpoint must be an HTTP(S) origin without credentials, query, or path")
    return url.rstrip("/")


def payload(modality: str, model: str, *, voice: str = "alloy", audio: bytes = b"") -> tuple[str, bytes, str]:
    if not model.strip():
        raise SmokeFailure("model name required")
    if modality == "chat":
        request = {"model": model, "messages": [{"role": "user", "content": "Reply with OK."}],
                   "max_tokens": 16, "stream": False}
        return "/v1/chat/completions", json.dumps(request).encode(), "application/json"
    if modality == "embedding":
        return "/v1/embeddings", json.dumps({"model": model,"input":"ModelOps infrastructure health check"}).encode(), "application/json"
    if modality == "speech":
        return "/v1/audio/speech", json.dumps({"model": model,"input":"Health check.","voice":voice}).encode(), "application/json"
    if modality != "transcription":
        raise SmokeFailure("unsupported modality")
    if not audio or len(audio) < 44:
        raise SmokeFailure("transcription requires nonempty WAV payload")
    boundary = "modelops-" + uuid.uuid4().hex
    b = boundary.encode()
    body = (b"--"+b+b"\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n"+model.encode()+
            b"\r\n--"+b+b"\r\nContent-Disposition: form-data; name=\"file\"; filename=\"sample.wav\"\r\n"+
            b"Content-Type: audio/wav\r\n\r\n"+audio+b"\r\n--"+b+b"--\r\n")
    return "/v1/audio/transcriptions", body, f"multipart/form-data; boundary={boundary}"


def validate_response(modality: str, data: bytes, content_type: str) -> dict:
    if modality == "speech":
        if not data or len(data) < 44 or not (content_type.lower().startswith("audio/") or content_type=="application/octet-stream"):
            raise SmokeFailure("speech endpoint did not return plausible audio")
        return {"audio_bytes":len(data)}
    try:
        response=json.loads(data)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SmokeFailure("server did not return valid JSON") from exc
    if not isinstance(response,dict):
        raise SmokeFailure("server response must be JSON object")
    if modality=="chat":
        choices=response.get("choices")
        if not isinstance(choices,list) or not choices or not isinstance(choices[0],dict):
            raise SmokeFailure("chat endpoint returned no choices")
        message=choices[0].get("message",{})
        if not isinstance(message,dict) or not isinstance(message.get("content"),str) or not message["content"].strip():
            raise SmokeFailure("chat endpoint returned empty content")
        return {"choices":len(choices),"nonempty_text":True}
    if modality=="embedding":
        rows=response.get("data")
        if not isinstance(rows,list) or not rows:
            raise SmokeFailure("embedding endpoint returned no vectors")
        vector=rows[0].get("embedding") if isinstance(rows[0],dict) else None
        if not isinstance(vector,list) or len(vector)<2 or any(isinstance(x,bool) or not isinstance(x,(float,int)) for x in vector):
            raise SmokeFailure("embedding endpoint returned invalid vector")
        return {"dimensions":len(vector)}
    if modality=="transcription":
        if not isinstance(response.get("text"),str) or not response["text"].strip():
            raise SmokeFailure("transcription endpoint returned empty text")
        return {"nonempty_text":True}
    raise SmokeFailure("unsupported modality")


def probe(origin: str, modality: str, model: str, key: str, timeout: float, *,
          audio: bytes = b"", voice: str = "alloy") -> dict:
    origin=check_origin(origin)
    endpoint, body, content_type=payload(modality,model,voice=voice,audio=audio)
    headers={"Content-Type":content_type,"Accept":"application/json" if modality!="speech" else "audio/*"}
    if key:
        headers["Authorization"]="Bearer "+key
    t0=time.monotonic()
    request=Request(origin+endpoint,data=body,headers=headers,method="POST")
    try:
        with urlopen(request,timeout=timeout) as response:
            code=response.status
            got_type=response.headers.get("Content-Type","").split(";")[0].strip()
            data=response.read(8*1024*1024+1)
    except HTTPError as exc:
        # The body may contain credentials/sensitive data; omit it.
        raise SmokeFailure(f"HTTP {exc.code}") from exc
    except (URLError,TimeoutError,OSError) as exc:
        raise SmokeFailure("network or serving endpoint failure") from exc
    if code!=200 or len(data)>8*1024*1024:
        raise SmokeFailure("HTTP status failure or response exceeds safe limit")
    details=validate_response(modality,data,got_type)
    return {"modality":modality,"model":model,"status":"PASS",
            "latency_ms":round((time.monotonic()-t0)*1000,3),**details}


def main(argv=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url",required=True)
    for mod in MODALITIES:
        ap.add_argument("--"+mod+"-model",default="")
    ap.add_argument("--audio-sample",type=Path)
    ap.add_argument("--voice",default="alloy")
    ap.add_argument("--api-key-env",default="MODEL_OPS_API_KEY")
    ap.add_argument("--timeout-s",type=float,default=30.)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args(argv)
    selected={mod:getattr(a,mod.replace("-","_")+"_model") for mod in MODALITIES}
    try:
        check_origin(a.base_url)
        if not any(selected.values()):
            raise SmokeFailure("at least one --*-model is required")
        if a.timeout_s<=0 or a.timeout_s>300:
            raise SmokeFailure("timeout must be positive and at most 300 s")
        audio=a.audio_sample.read_bytes() if selected["transcription"] and a.audio_sample else b""
    except (SmokeFailure,OSError) as exc:
        print(f"Smoke setup failed: {exc}",file=sys.stderr)
        return 2
    key=os.environ.get(a.api_key_env,"")
    outcome={"schema":"modelops.smoke.v1","executed_at_utc":datetime.now(timezone.utc).isoformat(),
             "origin":a.base_url,"status":"FAIL","results":[]}
    failed=False
    for modality,model in selected.items():
        if not model:
            continue
        try:
            outcome["results"].append(probe(a.base_url,modality,model,key,a.timeout_s,audio=audio,voice=a.voice))
        except SmokeFailure as exc:
            failed=True
            outcome["results"].append({"modality":modality,"model":model,"status":"FAIL","reason":str(exc)})
    outcome["status"]="FAIL" if failed else "PASS"
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(outcome,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":outcome["status"],"modalities":len(outcome["results"])}))
    return 1 if failed else 0


if __name__=="__main__":
    raise SystemExit(main())
