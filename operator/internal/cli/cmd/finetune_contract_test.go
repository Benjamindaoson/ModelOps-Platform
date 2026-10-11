package cmd

import (
	"strings"
	"testing"
)

func TestTemplateBoundDefaultsDoNotTriggerRejectedOverrides(t *testing.T) {
	ftr := buildTemplateBoundFineTuneRun("Qwen/Qwen2.5-0.5B-Instruct", "qwen-ft", "lora",
		"s3://datasets/train/", "alpaca", false, 0)
	if ftr.Spec.Training.Epochs != 0 || ftr.Spec.Resources.Memory != "" || ftr.Spec.Resources.GPU != 0 {
		t.Fatalf("must use Helm template configuration, not hard-coded CLI defaults: %+v", ftr.Spec)
	}
	if !ftr.Spec.Evaluation.Enabled || !ftr.Spec.QualityGate.Enabled {
		t.Fatal("model training must include quality evaluation")
	}
}

func TestTemplateBoundCLIRejectsUnsupportedOverrides(t *testing.T) {
	for _, flag := range []string{"epochs", "batch-size", "learning-rate", "lora-rank", "lora-alpha", "gpu"} {
		cmd := newFinetuneCreateCmd()
		value := "3"
		if flag == "learning-rate" { value = "1e-4" }
		if err := cmd.Flags().Set(flag,value); err != nil {t.Fatal(err)}
		if err := validateTemplateBoundFlags(cmd); err == nil || !strings.Contains(err.Error(),"cannot override") {
			t.Errorf("expected explicit unsupported override error for --%s; got %v",flag,err)
		}
	}
}

func TestTemplateBoundCLIRejectsDisabledQuality(t *testing.T) {
	for _,name := range []string{"eval","quality-gate"} {
		cmd:=newFinetuneCreateCmd()
		if err:=cmd.Flags().Set(name,"false");err!=nil {t.Fatal(err)}
		if err:=validateTemplateBoundFlags(cmd);err==nil {t.Errorf("disabled %s gate unexpectedly accepted",name)}
	}
}

func TestTemplateBoundNormalizesSourceAliases(t *testing.T) {
	ftr:=buildTemplateBoundFineTuneRun("base","name","lora","hf://tatsu-lab/alpaca","alpaca",false,0)
	if ftr.Spec.DataSource.Path!="tatsu-lab/alpaca" {t.Fatal(ftr.Spec.DataSource.Path)}
	ftr=buildTemplateBoundFineTuneRun("base","name","lora","minio://datasets/train/","alpaca",false,0)
	if ftr.Spec.DataSource.Path!="s3://datasets/train/" {t.Fatal(ftr.Spec.DataSource.Path)}
}
