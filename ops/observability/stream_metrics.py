"""Parse actual OpenAI SSE content/usage without treating frames as tokens."""
import json


class StreamMeter:
    def __init__(self, start, max_event_bytes=1024*1024):
        self.start = start
        self.max_event_bytes = max_event_bytes
        self.buffer = b""
        self.first_token_s = None
        self.output_tokens = None
        self.done = False
        self.error = None
        self.prompt_tokens = None
        self.content_times = []
        self.text = ""

    def feed(self, chunk, now):
        self.buffer += chunk
        while b"\n\n" in self.buffer:
            raw, self.buffer = self.buffer.split(b"\n\n", 1)
            if len(raw) > self.max_event_bytes:
                self.error = "oversized_sse_event"; self.buffer = b""; return
            parts = [line[5:].strip() for line in raw.splitlines() if line.startswith(b"data:")]
            if not parts: continue
            payload = b"\n".join(parts)
            if payload == b"[DONE]": self.done = True; continue
            try: obj = json.loads(payload)
            except (ValueError, UnicodeDecodeError):
                self.error = "invalid_sse_json"; continue
            if not isinstance(obj, dict):
                self.error = "invalid_sse_json"; continue
            if obj.get("error"): self.error = "upstream_stream_error"
            usage = obj.get("usage")
            if isinstance(usage, dict):
                inputs = usage.get("prompt_tokens")
                if isinstance(inputs, int) and not isinstance(inputs, bool) and inputs >= 0: self.prompt_tokens = inputs
            if usage is not None:
                tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
                if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0: self.output_tokens = tokens
                else: self.error = "invalid_token_usage"
            content = any(choice.get("text") or choice.get("delta", {}).get("content") for choice in obj.get("choices", []))
            if content:
                self.content_times.append(now)
                self.text += "".join(choice.get("text") or choice.get("delta", {}).get("content") or "" for choice in obj.get("choices", []))
            if content and self.first_token_s is None: self.first_token_s = max(0, now-self.start)
        if len(self.buffer) > self.max_event_bytes:
            self.error = "oversized_sse_event"; self.buffer = b""
