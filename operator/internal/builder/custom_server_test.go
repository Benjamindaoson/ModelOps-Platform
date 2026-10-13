package builder

import (
	v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
	"slices"
	"testing"
)

func TestCustomPolicyServerUsesDeclaredProtocol(t *testing.T) {
	md := newTestMD("smolvla", "lerobot/smolvla_libero", 1)
	md.Spec.Engine = "custom"
	md.Spec.Custom = &v1alpha1.CustomServerSpec{
		Image:   "example.invalid/modelops-policy@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		Command: []string{"python", "-m", "pipelines.robotics.serve"},
		Args:    []string{"--registry", "/private/registry", "--port", "8001"},
		Port:    8001, HealthPath: "/health",
	}
	if !SupportsServingEngine("custom") {
		t.Fatal("explicit custom engine rejected")
	}
	if err := ValidateServingSpec(md, "custom"); err != nil {
		t.Fatal(err)
	}
	dep := BuildDeployment(md, "custom", newTestPlatform())
	c := dep.Spec.Template.Spec.Containers[0]
	if c.Image != md.Spec.Custom.Image || c.Ports[0].ContainerPort != 8001 {
		t.Fatal("custom image/port lost")
	}
	if !slices.Equal(c.Command, md.Spec.Custom.Command) || !slices.Equal(c.Args, md.Spec.Custom.Args) {
		t.Fatal("action server replaced with LLM arguments")
	}
	if c.ReadinessProbe.HTTPGet.Path != "/health" {
		t.Fatal("custom readiness protocol lost")
	}
}

func TestCustomPolicyRefusesUnpinnedImageAndLLMCanary(t *testing.T) {
	md := newTestMD("smolvla", "lerobot/smolvla_libero", 1)
	if ValidateServingSpec(md, "custom") == nil {
		t.Fatal("missing custom configuration accepted")
	}
	md.Spec.Custom = &v1alpha1.CustomServerSpec{Image: "untrusted:latest", Command: []string{"python"}, Port: 8000, HealthPath: "/health"}
	if ValidateServingSpec(md, "custom") == nil {
		t.Fatal("mutable custom image accepted")
	}
}

func TestUnifiedQuantizationAndCacheReachVLLM(t *testing.T) {
	md := newTestMD("qwen", "Qwen/model", 1)
	md.Spec.Quantization = "awq"
	md.Spec.Cache = &v1alpha1.ServingCacheSpec{PrefixCaching: true}
	dep := BuildDeployment(md, "vllm", newTestPlatform())
	args := dep.Spec.Template.Spec.Containers[0].Args
	if !slices.Contains(args, "--quantization") || !slices.Contains(args, "awq") || !slices.Contains(args, "--enable-prefix-caching") {
		t.Fatal(args)
	}
}
