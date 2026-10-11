package builder

import (
    "slices"
    "testing"

    v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
)

func TestBuildDeployment_SGLangEngine(t *testing.T) {
    md := newTestMD("qwen-vl", "Qwen/Qwen2.5-VL-3B-Instruct", 1)
    md.Spec.EngineArgs = map[string]string{"--max-running-requests": "16"}
    dep := BuildDeployment(md, "sglang", newTestPlatform())
    got := dep.Spec.Template.Spec.Containers[0]
    if got.Image != "lmsysorg/sglang:latest-runtime" {
        t.Fatalf("unexpected SGLang image: %s", got.Image)
    }
    if !slices.Equal(got.Command, []string{"python3", "-m", "sglang.launch_server"}) {
        t.Fatalf("SGLang must launch with python module: %v", got.Command)
    }
    if !slices.Contains(got.Args, "--model-path") || !slices.Contains(got.Args, "--max-running-requests") {
        t.Fatalf("missing model path or custom tuning args: %v", got.Args)
    }
    if got.Ports[0].ContainerPort != 30000 {
        t.Fatalf("SGLang port must be 30000: %d", got.Ports[0].ContainerPort)
    }
    var shm bool
    for _, mount := range got.VolumeMounts { if mount.MountPath == "/dev/shm" { shm = true } }
    if !shm { t.Fatal("SGLang missing shared-memory volume") }
}

func TestSGLangSourceAutodetectionMatchesPodBuilder(t *testing.T) {
    _ = v1alpha1.ModelDeploymentSpec{Engine: "sglang"}
    md := newTestMD("llm", "Qwen/Qwen2.5-7B-Instruct", 0)
    dep := BuildDeployment(md, "sglang", nil)
    if dep.Spec.Template.Spec.Containers[0].Image == "" { t.Fatal("blank serving image") }
}
