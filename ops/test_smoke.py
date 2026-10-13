"""A local stub HTTP server exercises the protocol contract; this is NOT a model inference test."""
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ops.smoke import SmokeFailure,check_origin,payload,probe,validate_response

class FakeHTTP(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_POST(self):
        n=int(self.headers.get("Content-Length",0))
        self.rfile.read(n)
        if self.path.endswith("/chat/completions"):
            body=json.dumps({"choices":[{"message":{"content":"OK"}}]}).encode()
            content_type="application/json"
        elif self.path.endswith("/embeddings"):
            body=json.dumps({"data":[{"embedding":[0.1,0.2,0.3]}]}).encode()
            content_type="application/json"
        elif self.path.endswith("/audio/transcriptions"):
            body=json.dumps({"text":"recognized"}).encode()
            content_type="application/json"
        elif self.path.endswith("/audio/speech"):
            body=b"RIFF"+bytes(100)
            content_type="audio/wav"
        else:
            self.send_error(404);return
        self.send_response(200)
        self.send_header("Content-Type",content_type)
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)

class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),FakeHTTP)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f"http://127.0.0.1:{cls.server.server_port}"
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
    def test_all_family_protocol_shapes(self):
        for mode in ("chat","embedding","transcription","speech"):
            with self.subTest(modality=mode):
                got=probe(self.url,mode,"example","",5,audio=b"RIFF"+bytes(100))
                self.assertEqual(got["status"],"PASS")
                self.assertGreaterEqual(got["latency_ms"],0)
    def test_reject_url_credentials(self):
        with self.assertRaises(SmokeFailure):
            check_origin("http://alice:secret@127.0.0.1:8000")
    def test_bad_choice_rejected(self):
        with self.assertRaises(SmokeFailure):
            validate_response("chat",b'{"choices":[]}',"application/json")
    def test_bad_embedding_rejected(self):
        with self.assertRaises(SmokeFailure):
            validate_response("embedding",b'{"data":[{"embedding":["not-a-float"]}]}',"application/json")
    def test_empty_audio_rejected(self):
        with self.assertRaises(SmokeFailure):
            payload("transcription","asr",audio=b"")

if __name__=="__main__":
    unittest.main()
