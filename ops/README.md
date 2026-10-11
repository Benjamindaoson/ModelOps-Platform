# Real model API smoke suite

Run against a **live** OpenAI-compatible gateway / serving cluster. Each requested model type is verified against its actual API response contract and individual latency is captured. This checks request routing and response format; it does **not** measure speech quality, hallucinations, model accuracy, GPU efficiency or multi-node availability.

```bash
export MODEL_OPS_API_KEY="..." # from your secret manager, never commit
python ops/smoke.py --base-url http://127.0.0.1:4000 \
  --chat-model qwen-chat --embedding-model bge-m3 \
  --transcription-model whisper --audio-sample tests/assets/short_audio.wav \
  --speech-model kokoro --output evidence/smoke.json
```

Run just one or more models by omitting unused flags. ASR/TTS capability depends on a **real configured backend**; the imported Helm chart does not yet provide complete first-class ASR/TTS models, and such checks must not be counted as passing before service adapters are configured. All output excludes prompts, generated text, transcribed speech and API credentials. `ops/test_smoke.py` uses a stub local HTTP server to test response contracts only.

The generated report is sensitive to endpoint names/architecture and should not be publicly shared without review.
