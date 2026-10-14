"""Only completed, content-verified measurement points may be reused."""
from .contracts import digest
def valid_receipt(body,folder,source_sha,protocol_sha):
    try:
        return body["status"]=="PASS" and body["source_sha"]==source_sha and body["protocol_sha"]==protocol_sha and body["raw_sha"]==digest(folder/"requests.jsonl") and body["gpu_sha"]==digest(folder/"gpu.json")
    except (KeyError,OSError,TypeError):return False
