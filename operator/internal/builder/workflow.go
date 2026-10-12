/*
Copyright 2026.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package builder

import (
	"fmt"
	"strings"

	v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
)

// BuildArgoWorkflow creates an Argo Workflow that references the Helm-managed WorkflowTemplate.
// It also injects parameters from the FineTuneRun spec for fine-grained control.
// Dynamic runs share exactly the same parameter names as the product Control API.
func IsDynamicFineTuneRun(ftr *v1alpha1.FineTuneRun) bool {
	return ftr.Spec.BaseRevision != "" || ftr.Spec.BaseDigest != "" || ftr.Spec.DataSource.Digest != ""
}

func BuildArgoWorkflow(ftr *v1alpha1.FineTuneRun, releaseName string) *unstructured.Unstructured {
	outputTrunc := ftr.Spec.OutputName
	if len(outputTrunc) > 8 {
		outputTrunc = outputTrunc[:8]
	}
	name := strings.TrimRight(fmt.Sprintf("%s-%s", ftr.Name, outputTrunc), "-")

	// The dynamic Argo template is the same one called from FastAPI.
	// The legacy template remains available for existing explicitly fixed releases.
	parameters := buildWorkflowParameters(ftr)
	templateName := releaseName + "-finetune"
	if IsDynamicFineTuneRun(ftr) {
		templateName = "modelops-finetune-dynamic"
		parameters = DynamicWorkflowParameters(ftr)
	}

	wf := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "argoproj.io/v1alpha1",
			"kind":       "Workflow",
			"metadata": map[string]interface{}{
				"name":      name,
				"namespace": ftr.Namespace,
				"labels": map[string]interface{}{
					"app.kubernetes.io/name":     "finetune",
					"app.kubernetes.io/part-of": "modelops-platform",
					"modelops.io/finetunerun":   ftr.Name,
				},
				"annotations": map[string]string{
					"modelops.io/base-model":  ftr.Spec.BaseModel,
					"modelops.io/output-name": ftr.Spec.OutputName,
					"modelops.io/method":     ftr.Spec.Method,
				},
			},
			"spec": map[string]interface{}{
				"workflowTemplateRef": map[string]interface{}{
					"name": templateName,
				},
			},
		},
	}

	// Add parameters if any are defined
	if len(parameters) > 0 {
		spec := wf.Object["spec"].(map[string]interface{})
		spec["arguments"] = map[string]interface{}{
			"parameters": parameters,
		}
	}

	return wf
}

// buildDynamicWorkflowParameters follows the single Argo contract
// shared with control-plane/modelops/runtime.py (underscored parameter names).
// Validation is performed in the controller BEFORE this helper is called.
func DynamicWorkflowParameters(ftr *v1alpha1.FineTuneRun) []map[string]string {
	t := ftr.Spec.Training
	method := ftr.Spec.Method
	if method == "" { method = "lora" }
	values := []struct{name, value string}{
		{"base_model", ftr.Spec.BaseModel},
		{"base_revision", ftr.Spec.BaseRevision},
		{"base_sha256", ftr.Spec.BaseDigest},
		{"dataset_uri", ftr.Spec.DataSource.Path},
		{"dataset_sha256", ftr.Spec.DataSource.Digest},
		{"method", method},
		{"output_name", ftr.Spec.OutputName},
		{"epochs", fmt.Sprintf("%d", t.Epochs)},
		{"batch_size", fmt.Sprintf("%d", t.BatchSize)},
		{"learning_rate", t.LearningRate},
		{"lora_rank", fmt.Sprintf("%d", t.LoraRank)},
		{"lora_alpha", fmt.Sprintf("%d", t.LoraAlpha)},
		{"gpu", fmt.Sprintf("%d", ftr.Spec.Resources.GPU)},
		{"gradient_accumulation_steps", fmt.Sprintf("%d", t.GradientAccumulationSteps)},
		{"min_token_f1", ftr.Spec.Evaluation.MinTokenF1},
	}
	parameters := make([]map[string]string,0,len(values))
	for _,v := range values { parameters = append(parameters,map[string]string{"name":v.name,"value":v.value}) }
	return parameters
}

// buildWorkflowParameters converts FineTuneRun spec to Argo Workflow parameters.
func buildWorkflowParameters(ftr *v1alpha1.FineTuneRun) []map[string]string {
	var params []map[string]string

	// Base model
	params = append(params, map[string]string{
		"name":  "base-model",
		"value": ftr.Spec.BaseModel,
	})

	// Output name
	params = append(params, map[string]string{
		"name":  "output-name",
		"value": ftr.Spec.OutputName,
	})

	// Method
	method := ftr.Spec.Method
	if method == "" {
		method = "lora"
	}
	params = append(params, map[string]string{
		"name":  "method",
		"value": method,
	})

	// Data source
	params = append(params, map[string]string{
		"name":  "data-source-type",
		"value": ftr.Spec.DataSource.Type,
	})
	if ftr.Spec.DataSource.Path != "" {
		params = append(params, map[string]string{
			"name":  "data-source-path",
			"value": ftr.Spec.DataSource.Path,
		})
	}
	if ftr.Spec.DataSource.Format != "" {
		params = append(params, map[string]string{
			"name":  "data-source-format",
			"value": ftr.Spec.DataSource.Format,
		})
	}

	// Training hyperparameters (only if explicitly set)
	training := ftr.Spec.Training
	if training.Epochs > 0 {
		params = append(params, map[string]string{
			"name":  "epochs",
			"value": fmt.Sprintf("%d", training.Epochs),
		})
	}
	if training.BatchSize > 0 {
		params = append(params, map[string]string{
			"name":  "batch-size",
			"value": fmt.Sprintf("%d", training.BatchSize),
		})
	}
	if training.LearningRate != "" {
		params = append(params, map[string]string{
			"name":  "learning-rate",
			"value": training.LearningRate,
		})
	}
	if training.GradientAccumulationSteps > 0 {
		params = append(params, map[string]string{
			"name":  "gradient-accumulation-steps",
			"value": fmt.Sprintf("%d", training.GradientAccumulationSteps),
		})
	}
	if training.WarmupRatio != "" {
		params = append(params, map[string]string{
			"name":  "warmup-ratio",
			"value": training.WarmupRatio,
		})
	}
	if training.LoraRank > 0 {
		params = append(params, map[string]string{
			"name":  "lora-rank",
			"value": fmt.Sprintf("%d", training.LoraRank),
		})
	}
	if training.LoraAlpha > 0 {
		params = append(params, map[string]string{
			"name":  "lora-alpha",
			"value": fmt.Sprintf("%d", training.LoraAlpha),
		})
	}
	if training.LoraTarget != "" {
		params = append(params, map[string]string{
			"name":  "lora-target",
			"value": training.LoraTarget,
		})
	}

	// Resources
	resources := ftr.Spec.Resources
	if resources.GPU > 0 {
		params = append(params, map[string]string{
			"name":  "gpu-count",
			"value": fmt.Sprintf("%d", resources.GPU),
		})
	}
	if resources.Memory != "" {
		params = append(params, map[string]string{
			"name":  "memory-limit",
			"value": resources.Memory,
		})
	}

	// Evaluation
	if ftr.Spec.Evaluation.Enabled {
		params = append(params, map[string]string{
			"name":  "run-evaluation",
			"value": "true",
		})
		if ftr.Spec.Evaluation.Dataset != "" {
			params = append(params, map[string]string{
				"name":  "evaluation-dataset",
				"value": ftr.Spec.Evaluation.Dataset,
			})
		}
	}

	// Quality gate
	if ftr.Spec.QualityGate.Enabled {
		params = append(params, map[string]string{
			"name":  "run-quality-gate",
			"value": "true",
		})
		thresholds := ftr.Spec.QualityGate.Thresholds
		if thresholds.MinEvalLoss != "" {
			params = append(params, map[string]string{
				"name":  "min-eval-loss",
				"value": thresholds.MinEvalLoss,
			})
		}
		if thresholds.MaxTrainLoss != "" {
			params = append(params, map[string]string{
				"name":  "max-train-loss",
				"value": thresholds.MaxTrainLoss,
			})
		}
	}

	// Auto deploy
	if ftr.Spec.Deploy.Enabled {
		params = append(params, map[string]string{
			"name":  "auto-deploy",
			"value": "true",
		})
		if ftr.Spec.Deploy.CanaryWeight > 0 {
			params = append(params, map[string]string{
				"name":  "canary-weight",
				"value": fmt.Sprintf("%d", ftr.Spec.Deploy.CanaryWeight),
			})
		}
	}

	return params
}
