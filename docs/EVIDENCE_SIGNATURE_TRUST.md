# ModelOps model-evaluation signature trust boundary

## Production: Ed25519, verifier-only API

**Do not share the evaluation Worker private key with API, Console, ingress
or the public web.** Production ModelOps refuses HMAC attestations. The Control
API reads **only the base64-encoded 32-byte Ed25519 public key** from external
Secret \`MODELOPS_EVIDENCE_VERIFY_KEY\`. The authorized evaluation Worker uses
the separate Ed25519 PKCS#8 private key and sends its detached base64 signature
in \`X-ModelOps-Attestation\`.

The signed message is ASCII lowercase SHA-256 hex of the canonical UTF-8 JSON:

\`\`\`python
hashlib.sha256(json.dumps(report, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode()).hexdigest().encode("ascii")
\`\`\`

The API validates the signature, artifact/dataset digest binding, non-overlap
condition, sample count, finite metrics, and independent two-person release
approval. This **does not certify the worker really ran**; it ensures an
ordinary authenticated API operator cannot self-sign a passing report without
the separately protected private key. Signers must remain a trusted, audited
service; protect their job environment, run inputs and signing permissions.

## Trusted Worker signing CLI

The evaluator's private key must be a root-/worker-protected file mode 0600.
Do NOT paste the key into a chat, GitHub Issue, Helm Values, logs or CI output.

\`\`\`bash
python pipelines/evaluation/sign_report.py \\
  --report /restricted/worker/eval-report.json \\
  --private-key-file /run/secrets/modelops-eval-private.pem \\
  --signature-output /restricted/worker/attestation.sig
\`\`\`

The signature file is public and can be attached to the authenticated
\`POST /api/v1/evaluations/attest\` request. Mount the public key *only* in the
API Kubernetes environment, not the private one. To rotate the signer:
publish the new public key with a planned overlap/rollout and reattest
artifacts as required by release policy. An invalid signature blocks approval.

HMAC \`MODELOPS_ATTESTATION_KEY\` remains supported **only in development/test**
to preserve deterministic offline contract testing. It must never be used for
real production release evidence.
