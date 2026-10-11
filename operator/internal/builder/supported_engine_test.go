package builder

import "testing"

func TestSupportedServingEngines(t *testing.T){
    for _,name:=range []string{"vllm","sglang","tei","llamacpp"} {
        if !SupportsServingEngine(name) {t.Errorf("supported engine unexpectedly missing: %s",name)}
    }
    for _,name:=range []string{"","chitu","tensorRT-LLM","unknown"} {
        if SupportsServingEngine(name) {t.Errorf("unsupported engine must be denied: %s",name)}
    }
}
