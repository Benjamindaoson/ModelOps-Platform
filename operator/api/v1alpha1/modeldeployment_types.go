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

package v1alpha1

import (
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
)

// ModelDeploymentSpec defines the desired state of a model deployment.
type ModelDeploymentSpec struct {
	// Source is the HuggingFace model ID or path (e.g. "Qwen/Qwen2.5-7B-Instruct").
	// +kubebuilder:validation:Required
	// +kubebuilder:validation:MinLength=1
	Source string `json:"source"`

	// Engine selects the inference engine. "auto" detects from source name.
	// +kubebuilder:validation:Enum=auto;vllm;sglang;tei;llamacpp
	// +kubebuilder:default="auto"
	// +optional
	Engine string `json:"engine,omitempty"`

	// Replicas is the desired number of model serving pods.
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:default=1
	// +optional
	Replicas *int32 `json:"replicas,omitempty"`

	// Resources specifies compute resources for the model serving container.
	// +optional
	Resources ModelResources `json:"resources,omitempty"`

	// Accelerator selects the GPU vendor for scheduling.
	// +kubebuilder:validation:Enum=nvidia;amd;gaudi
	// +kubebuilder:default="nvidia"
	// +optional
	Accelerator string `json:"accelerator,omitempty"`

	// MIGDevice specifies an NVIDIA MIG device resource name, overriding the gpu field.
	// +optional
	MIGDevice string `json:"migDevice,omitempty"`

	// EngineArgs are extra CLI arguments passed to the inference engine.
	// +optional
	EngineArgs map[string]string `json:"engineArgs,omitempty"`

	// PrefixCaching enables vLLM automatic prefix caching.
	// +optional
	PrefixCaching bool `json:"prefixCaching,omitempty"`

	// Spot configures spot/preemptible GPU scheduling.
	// +optional
	Spot *SpotConfig `json:"spot,omitempty"`

	// Canary configures a canary deployment for A/B traffic splitting.
	// +optional
	Canary *CanaryConfig `json:"canary,omitempty"`

	// ModelStore overrides the platform-level model store configuration.
	// +optional
	ModelStore *ModelStoreOverride `json:"modelStore,omitempty"`

	// AutoScaling configures automatic scaling for this model.
	// +optional
	AutoScaling *AutoScalingSpec `json:"autoScaling,omitempty"`
}

// ModelResources defines compute resources for model serving.
type ModelResources struct {
	// GPU is the number of GPUs to request (0 for CPU-only).
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:default=1
	// +optional
	GPU int32 `json:"gpu,omitempty"`

	// Memory is the memory limit (e.g. "16Gi").
	// +kubebuilder:default="16Gi"
	// +optional
	Memory string `json:"memory,omitempty"`

	// CPU is the CPU limit (e.g. "4").
	// +kubebuilder:default="4"
	// +optional
	CPU string `json:"cpu,omitempty"`
}

// SpotConfig configures spot/preemptible GPU scheduling.
type SpotConfig struct {
	// Enabled enables spot instance scheduling.
	// +optional
	Enabled bool `json:"enabled,omitempty"`

	// Provider selects the cloud provider for spot tolerations.
	// +kubebuilder:validation:Enum=aws;gcp;azure;karpenter
	// +optional
	Provider string `json:"provider,omitempty"`
}

// CanaryConfig configures canary deployment with traffic splitting.
type CanaryConfig struct {
	// Source is the HuggingFace model ID for the canary model.
	// +kubebuilder:validation:Required
	Source string `json:"source"`

	// Revision identifies a pinned model snapshot. For HF this is the commit SHA.
	// +kubebuilder:validation:MinLength=7
	Revision string `json:"revision"`

	// Digest is the verified SHA-256 of the candidate checkpoint tree.
	// +kubebuilder:validation:Pattern=^[a-f0-9]{64}$
	Digest string `json:"digest"`

	// Weight is the percentage of traffic routed to the canary (0-100).
	// +kubebuilder:validation:Minimum=0
	// +kubebuilder:validation:Maximum=100
	Weight int32 `json:"weight"`

	// Resources for the canary deployment.
	// +optional
	Resources ModelResources `json:"resources,omitempty"`
}

// ModelStoreOverride allows per-model override of model store settings.
type ModelStoreOverride struct {
	// Endpoint is the MinIO endpoint (e.g. "kube-llmops-minio:9000").
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// Bucket is the MinIO bucket name.
	// +optional
	Bucket string `json:"bucket,omitempty"`
}

// AutoScalingSpec defines automatic scaling configuration.
type AutoScalingSpec struct {
	// Enabled enables automatic scaling.
	// +optional
	Enabled bool `json:"enabled,omitempty"`

	// MinReplicas is the minimum number of replicas.
	// +optional
	MinReplicas *int32 `json:"minReplicas,omitempty"`

	// MaxReplicas is the maximum number of replicas.
	// +optional
	MaxReplicas *int32 `json:"maxReplicas,omitempty"`

	// UseKEDA enables KEDA-based autoscaling instead of HPA.
	// +optional
	UseKEDA bool `json:"useKEDA,omitempty"`

	// ScaleTargetCPUUtilizationPercentage is the target CPU utilization for HPA.
	// +optional
	ScaleTargetCPUUtilizationPercentage *int32 `json:"scaleTargetCPUUtilizationPercentage,omitempty"`

	// ScaleTargetMemoryUtilizationPercentage is the target memory utilization for HPA.
	// +optional
	ScaleTargetMemoryUtilizationPercentage *int32 `json:"scaleTargetMemoryUtilizationPercentage,omitempty"`

	// KEDATriggers defines KEDA-specific trigger configuration.
	// +optional
	KEDATriggers *KEDATriggersSpec `json:"kedaTriggers,omitempty"`
}

// KEDATriggersSpec defines KEDA-specific trigger configuration.
type KEDATriggersSpec struct {
	// QueueDepthEnabled enables scaling based on vLLM queue depth.
	// +optional
	QueueDepthEnabled bool `json:"queueDepthEnabled,omitempty"`

	// QueueDepthMetric is the Prometheus metric name for queue depth.
	// +optional
	QueueDepthMetric string `json:"queueDepthMetric,omitempty"`

	// QueueDepthThreshold is the threshold for queue depth scaling.
	// +optional
	QueueDepthThreshold *int32 `json:"queueDepthThreshold,omitempty"`

	// TTFTEnabled enables scaling based on TTFT P95 latency.
	// +optional
	TTFTEnabled bool `json:"ttftEnabled,omitempty"`

	// TTFTThreshold is the TTFT P95 threshold in seconds.
	// +optional
	TTFTThreshold *float64 `json:"ttftThreshold,omitempty"`

	// TPOTEnabled enables scaling based on TPOT P95 latency.
	// +optional
	TPOTEnabled bool `json:"tpotEnabled,omitempty"`

	// TPOTThreshold is the TPOT P95 threshold in seconds.
	// +optional
	TPOTThreshold *float64 `json:"tpotThreshold,omitempty"`
}

// ModelDeploymentStatus defines the observed state of ModelDeployment.
type ModelDeploymentStatus struct {
	// Phase is the high-level lifecycle phase.
	// +kubebuilder:validation:Enum=Pending;Downloading;Deploying;Ready;Degraded;Failed
	// +optional
	Phase string `json:"phase,omitempty"`

	// Engine is the resolved engine after auto-detection.
	// +optional
	Engine string `json:"engine,omitempty"`

	// Endpoint is the in-cluster URL for the model's API.
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// ReadyReplicas is the number of ready model serving pods.
	// +optional
	ReadyReplicas int32 `json:"readyReplicas,omitempty"`

	// TotalReplicas is the desired number of replicas.
	// +optional
	TotalReplicas int32 `json:"totalReplicas,omitempty"`

	// ModelSize is the discovered model size after download.
	// +optional
	ModelSize string `json:"modelSize,omitempty"`

	// DownloadProgress holds download progress information.
	// +optional
	DownloadProgress *DownloadProgress `json:"downloadProgress,omitempty"`

	// InitContainerStatus holds the init container state.
	// +optional
	InitContainerStatus InitContainerStatus `json:"initContainerStatus,omitempty"`

	// Conditions represent the latest observations of the resource's state.
	// +optional
	Conditions []metav1.Condition `json:"conditions,omitempty"`

	// Canary holds the status of the canary deployment.
	// +optional
	Canary *CanaryStatus `json:"canary,omitempty"`
}

// DownloadProgress holds download progress information.
type DownloadProgress struct {
	// StartTime is when the download started.
	// +optional
	StartTime *metav1.Time `json:"startTime,omitempty"`

	// CompletionTime is when the download completed.
	// +optional
	CompletionTime *metav1.Time `json:"completionTime,omitempty"`

	// BytesDownloaded is the number of bytes downloaded.
	// +optional
	BytesDownloaded int64 `json:"bytesDownloaded,omitempty"`

	// TotalBytes is the total size in bytes.
	// +optional
	TotalBytes int64 `json:"totalBytes,omitempty"`

	// Percentage is the download progress percentage.
	// +optional
	Percentage int32 `json:"percentage,omitempty"`
}

// InitContainerStatus holds the state of the init container.
type InitContainerStatus struct {
	// Phase is the init container phase (Pending, Running, Terminated).
	// +optional
	Phase string `json:"phase,omitempty"`

	// Message contains progress message.
	// +optional
	Message string `json:"message,omitempty"`
}

// CanaryStatus holds the observed state of the canary deployment.
type CanaryStatus struct {
	// Phase is the canary deployment phase.
	// +optional
	Phase string `json:"phase,omitempty"`

	// Endpoint is the in-cluster URL for the canary model API.
	// +optional
	Endpoint string `json:"endpoint,omitempty"`

	// ReadyReplicas is the number of ready canary pods.
	// +optional
	ReadyReplicas int32 `json:"readyReplicas,omitempty"`
}

// +kubebuilder:object:root=true
// +kubebuilder:subresource:status
// +kubebuilder:resource:shortName=md
// +kubebuilder:printcolumn:name="Engine",type=string,JSONPath=`.status.engine`
// +kubebuilder:printcolumn:name="Replicas",type=string,JSONPath=`.status.readyReplicas`
// +kubebuilder:printcolumn:name="Phase",type=string,JSONPath=`.status.phase`
// +kubebuilder:printcolumn:name="Endpoint",type=string,JSONPath=`.status.endpoint`,priority=1
// +kubebuilder:printcolumn:name="Age",type=date,JSONPath=`.metadata.creationTimestamp`

// ModelDeployment is the Schema for the modeldeployments API.
type ModelDeployment struct {
	metav1.TypeMeta   `json:",inline"`
	metav1.ObjectMeta `json:"metadata,omitempty"`

	Spec   ModelDeploymentSpec   `json:"spec,omitempty"`
	Status ModelDeploymentStatus `json:"status,omitempty"`
}

// +kubebuilder:object:root=true

// ModelDeploymentList contains a list of ModelDeployment.
type ModelDeploymentList struct {
	metav1.TypeMeta `json:",inline"`
	metav1.ListMeta `json:"metadata,omitempty"`
	Items           []ModelDeployment `json:"items"`
}

func init() {
	SchemeBuilder.Register(&ModelDeployment{}, &ModelDeploymentList{})
}
