import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from fastapi.testclient import TestClient
from ops.observability.server import create_app

@pytest.fixture
def upstream():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            self.send_response(200);self.end_headers()
            self.wfile.write(json.dumps({"data":[{"id":"unit-id"}]}).encode() if self.path=="/v1/models" else b"{}")
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if body.get("model")=="bad-json":
                self.send_response(200);self.end_headers();self.wfile.write(b"not-json");return
            if body.get("model")=="http-error":
                self.send_response(503);self.end_headers();self.wfile.write(b"{}");return
            self.send_response(200);self.end_headers()
            if body.get("stream"):
                for obj in [{"choices":[{"delta":{"role":"assistant","content":""}}]},{"choices":[{"delta":{"content":"Paris"}}]},{"choices":[],"usage":{"completion_tokens":2}}]:
                    self.wfile.write(("data: "+json.dumps(obj)+"\n\n").encode())
                self.wfile.write(b"data: [DONE]\n\n")
            else:self.wfile.write(json.dumps({"model":"unit-id","choices":[{"message":{"content":"Paris"}}],"usage":{"completion_tokens":2}}).encode())
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown();thread.join();server.server_close()

def test_proxy_preserves_stream_and_records_actual_usage(upstream):
    with TestClient(create_app(upstream,"unit-v1")) as client:
        r=client.post("/v1/chat/completions",json={"model":"unit-id","stream":True,"messages":[]})
        assert r.status_code==200 and "Paris" in r.text and "[DONE]" in r.text
        metrics=client.get("/metrics").text
        assert 'modelops_inference_output_tokens_total{version="unit-v1"} 2.0' in metrics
        assert 'modelops_inference_ttft_seconds_count{version="unit-v1"} 1.0' in metrics
        assert 'modelops_inference_inflight{version="unit-v1"} 0.0' in metrics

def test_upstream_http_error_has_error_counter(upstream):
    with TestClient(create_app(upstream)) as client:
        assert client.post("/v1/completions",json={"model":"http-error"}).status_code==503
        assert 'reason="http"' in client.get("/metrics").text

def test_success_status_with_invalid_json_is_counted_as_error(upstream):
    with TestClient(create_app(upstream),raise_server_exceptions=False) as client:
        assert client.post("/v1/completions",json={"model":"bad-json"}).status_code==502
        assert 'reason="invalid_upstream_json"' in client.get("/metrics").text

def test_invalid_stream_options_is_rejected_before_opening_request(upstream):
    with TestClient(create_app(upstream),raise_server_exceptions=False) as client:
        assert client.post("/v1/completions",json={"model":"unit-id","stream":True,"stream_options":[]}).status_code==400

def test_health_and_model_identity_are_forwarded(upstream):
    with TestClient(create_app(upstream)) as client:
        assert client.get("/health").status_code==200
        assert client.get("/v1/models").json()["data"][0]["id"]=="unit-id"
