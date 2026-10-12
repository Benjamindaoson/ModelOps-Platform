{{- define "modelops.fullname" -}}modelops-control{{- end -}}

{{- define "modelops.validate" -}}
{{- if or (not .Values.api.image.repository) (not (regexMatch "^sha256:[a-f0-9]{64}$" (.Values.api.image.digest | default ""))) -}}
{{- fail "API OCI repository and immutable sha256 digest are mandatory" -}}
{{- end -}}
{{- if or (not .Values.console.image.repository) (not (regexMatch "^sha256:[a-f0-9]{64}$" (.Values.console.image.digest | default ""))) -}}
{{- fail "Console OCI repository and immutable sha256 digest are mandatory" -}}
{{- end -}}
{{- range $field := list "database" "evaluationVerify" -}}
  {{- $entry := index $.Values.secrets $field -}}
  {{- if or (not $entry.name) (not $entry.key) -}}
    {{- fail (printf "Existing %s Secret name and key are required" $field) -}}
  {{- end -}}
{{- end -}}
{{- if or (not (hasPrefix "https://" .Values.oidc.issuer)) (not (hasPrefix "https://" .Values.oidc.jwksUrl)) (not .Values.oidc.audience) (not .Values.oidc.clientId) -}}
{{- fail "Production requires HTTPS OIDC issuer/JWKS and nonempty audience/clientId" -}}
{{- end -}}
{{- if or (not .Values.ingress.host) (not .Values.ingress.tlsSecret) (not .Values.ingress.controllerNamespace) -}}
{{- fail "TLS ingress host, secret and controller namespace are mandatory" -}}
{{- end -}}
{{- if ne .Values.oidc.publicOrigin (printf "https://%s" .Values.ingress.host) -}}
{{- fail "Public origin must match HTTPS ingress host exactly" -}}
{{- end -}}
{{- if not .Values.networkPolicy.enabled -}}{{- fail "NetworkPolicy is mandatory" -}}{{- end -}}
{{- if or (not .Values.api.egressCidrs) (not .Values.console.egressCidrs) -}}
{{- fail "Explicit API and Console egress CIDRs are mandatory" -}}
{{- end -}}
{{- range $cidr := concat .Values.api.egressCidrs .Values.console.egressCidrs -}}
  {{- if not (regexMatch "^[0-9a-fA-F:.]+/[0-9]{1,3}$" $cidr) -}}
    {{- fail "Egress CIDRs must be explicit IP blocks" -}}
  {{- end -}}
{{- end -}}
{{- if lt (int .Values.api.replicas) 2 -}}{{- fail "API needs at least two replicas" -}}{{- end -}}
{{- if lt (int .Values.console.replicas) 2 -}}{{- fail "Console needs at least two replicas" -}}{{- end -}}
{{- if not .Values.tenants -}}{{- fail "Explicit tenant namespaces must be bootstrapped" -}}{{- end -}}
{{- range $tenant := .Values.tenants -}}
  {{- if not (regexMatch "^[a-z](?:[a-z0-9-]{0,38}[a-z0-9])?$" $tenant) -}}
    {{- fail "Invalid tenant namespace slug" -}}
  {{- end -}}
{{- end -}}
{{- end -}}
