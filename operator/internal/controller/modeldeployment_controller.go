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

package controller

import (
	"context"
	"fmt"
	"reflect"
	"strconv"
	"strings"
	"time"

	appsv1 "k8s.io/api/apps/v1"
	autoscalingv2 "k8s.io/api/autoscaling/v2"
	corev1 "k8s.io/api/core/v1"
	policyv1 "k8s.io/api/policy/v1"
	apierrors "k8s.io/apimachinery/pkg/api/errors"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	apimeta "k8s.io/apimachinery/pkg/api/meta"
	"k8s.io/apimachinery/pkg/runtime"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/apimachinery/pkg/types"
	"k8s.io/apimachinery/pkg/util/intstr"
	"k8s.io/utils/ptr"
	ctrl "sigs.k8s.io/controller-runtime"
	"sigs.k8s.io/controller-runtime/pkg/client"
	"sigs.k8s.io/controller-runtime/pkg/controller/controllerutil"
	logf "sigs.k8s.io/controller-runtime/pkg/log"

	v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
	"github.com/kube-llmops/operator/internal/builder"
	"github.com/kube-llmops/operator/internal/engine"
	"github.com/kube-llmops/operator/internal/gateway"
)

const modelDeploymentFinalizer = "llmops.kubellmops.io/finalizer"

// ModelDeploymentReconciler reconciles a ModelDeployment object.
type ModelDeploymentReconciler struct {
	client.Client
	Scheme        *runtime.Scheme
	GatewayClient gateway.Client
}

// +kubebuilder:rbac:groups=llmops.kubellmops.io,resources=modeldeployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=llmops.kubellmops.io,resources=modeldeployments/status,verbs=get;update;patch
// +kubebuilder:rbac:groups=llmops.kubellmops.io,resources=modeldeployments/finalizers,verbs=update
// +kubebuilder:rbac:groups=llmops.kubellmops.io,resources=llmplatforms,verbs=get;list;watch
// +kubebuilder:rbac:groups=apps,resources=deployments,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=services,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups="",resources=persistentvolumeclaims,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=autoscaling,resources=horizontalpodautoscalers,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=keda.sh,resources=scaledobjects,verbs=get;list;watch;create;update;patch;delete
// +kubebuilder:rbac:groups=policy,resources=poddisruptionbudgets,verbs=get;list;watch;create;update;patch;delete

// Reconcile moves the cluster state toward the desired ModelDeployment state.
func (r *ModelDeploymentReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
	log := logf.FromContext(ctx)

	// 1. Fetch the ModelDeployment
	md := &v1alpha1.ModelDeployment{}
	if err := r.Get(ctx, req.NamespacedName, md); err != nil {
		if apierrors.IsNotFound(err) {
			return ctrl.Result{}, nil
		}
		return ctrl.Result{}, err
	}

	// 2. Handle deletion
	if !md.DeletionTimestamp.IsZero() {
		if controllerutil.ContainsFinalizer(md, modelDeploymentFinalizer) {
			if r.GatewayClient != nil {
				if err := r.GatewayClient.DeregisterModel(ctx, md.Name); err != nil { return ctrl.Result{}, err }
				if md.Spec.Canary != nil {
					if err := r.GatewayClient.DeregisterModel(ctx, md.Name+"-canary"); err != nil { return ctrl.Result{}, err }
				}
			}
			controllerutil.RemoveFinalizer(md, modelDeploymentFinalizer)
			if err := r.Update(ctx, md); err != nil { return ctrl.Result{}, err }
		}
		return ctrl.Result{}, nil
	}

	// 3. Add finalizer if missing
	if !controllerutil.ContainsFinalizer(md, modelDeploymentFinalizer) {
		controllerutil.AddFinalizer(md, modelDeploymentFinalizer)
		if err := r.Update(ctx, md); err != nil {
			return ctrl.Result{}, err
		}
	}

	// 4. Resolve engine
	resolvedEngine := engine.ResolveEngine(md.Spec.Source, md.Spec.Engine)

	if !builder.SupportsServingEngine(resolvedEngine) {
		md.Status.Phase = "Failed"
		md.Status.Engine = resolvedEngine
		setCondition(&md.Status.Conditions, metav1.Condition{
			Type:               "ModelReady",
			Status:             metav1.ConditionFalse,
			Reason:             "UnsupportedServingEngine",
			Message:            "Requested engine is not implemented by the ModelDeployment Operator",
			LastTransitionTime: metav1.Now(),
			ObservedGeneration: md.Generation,
		})
		if err := r.Status().Update(ctx, md); err != nil { return ctrl.Result{}, err }
		return ctrl.Result{}, nil
	}

	// 5. Find LLMPlatform
	var platform *v1alpha1.LLMPlatform
	platformList := &v1alpha1.LLMPlatformList{}
	if err := r.List(ctx, platformList, client.InNamespace(md.Namespace)); err != nil {
		return ctrl.Result{}, err
	}
	if len(platformList.Items) > 0 { platform = &platformList.Items[0] }

	// 6. Ensure PVC
	pvc := builder.BuildPVC(md, resolvedEngine)
	existingPVC := &corev1.PersistentVolumeClaim{}
	if err := r.Get(ctx, types.NamespacedName{Name: pvc.Name, Namespace: pvc.Namespace}, existingPVC); err != nil {
		if apierrors.IsNotFound(err) {
			if err := controllerutil.SetControllerReference(md, pvc, r.Scheme); err != nil { return ctrl.Result{}, err }
			if err := r.Create(ctx, pvc); err != nil { return ctrl.Result{}, err }
			log.Info("created PVC", "name", pvc.Name)
		} else {
			return ctrl.Result{}, err
		}
	}

	// 7. Ensure Deployment
	desiredDep := builder.BuildDeployment(md, resolvedEngine, platform)
	existingDep := &appsv1.Deployment{}
	if err := r.Get(ctx, types.NamespacedName{Name: desiredDep.Name, Namespace: desiredDep.Namespace}, existingDep); err != nil {
		if apierrors.IsNotFound(err) {
			if err := controllerutil.SetControllerReference(md, desiredDep, r.Scheme); err != nil { return ctrl.Result{}, err }
			if err := r.Create(ctx, desiredDep); err != nil { return ctrl.Result{}, err }
			log.Info("created Deployment", "name", desiredDep.Name)
		} else {
			return ctrl.Result{}, err
		}
	} else {
		if !reflect.DeepEqual(existingDep.Spec, desiredDep.Spec) || !reflect.DeepEqual(existingDep.Labels, desiredDep.Labels) {
			existingDep.Spec = desiredDep.Spec
			existingDep.Labels = desiredDep.Labels
			if err := r.Update(ctx, existingDep); err != nil { return ctrl.Result{}, err }
		}
	}

	// 8. Ensure Service
	svc := builder.BuildService(md, resolvedEngine)
	existingSvc := &corev1.Service{}
	if err := r.Get(ctx, types.NamespacedName{Name: svc.Name, Namespace: svc.Namespace}, existingSvc); err != nil {
		if apierrors.IsNotFound(err) {
			if err := controllerutil.SetControllerReference(md, svc, r.Scheme); err != nil { return ctrl.Result{}, err }
			if err := r.Create(ctx, svc); err != nil { return ctrl.Result{}, err }
			log.Info("created Service", "name", svc.Name)
		} else {
			return ctrl.Result{}, err
		}
	}

	// 9. Ensure PDB
	if err := r.ensurePDB(ctx, md, md.Name); err != nil {
		return ctrl.Result{}, err
	}

	// 10. Handle Canary
	if md.Spec.Canary != nil {
		if err := r.reconcileCanary(ctx, md, resolvedEngine, platform); err != nil {
			return ctrl.Result{}, err
		}
	}

	// 11. Handle AutoScaling
	if err := r.reconcileAutoScaling(ctx, md, resolvedEngine); err != nil {
		return ctrl.Result{}, err
	}

	// 12. Update status
	if err := r.updateStatus(ctx, req, md, resolvedEngine); err != nil {
		return ctrl.Result{}, err
	}

	// 13. Register with gateway
	if md.Status.Phase == "Ready" {
		if r.GatewayClient == nil { return r.setGatewayDegraded(ctx, req, "GatewayNotConfigured") }
		if gatewayConditionUpToDate(md) {
			if err := r.GatewayClient.HealthCheck(ctx); err != nil {
				log.Error(err, "Gateway health check failed")
				return r.setGatewayDegraded(ctx, req, "GatewayHealthFailed")
			}
		} else {
			if err := r.registerWithGateway(ctx, md, resolvedEngine); err != nil {
				log.Error(err, "serving replicas ready but Gateway registration failed")
				return r.setGatewayDegraded(ctx, req, "GatewayRegistrationFailed")
			}
			if err := r.setGatewayReady(ctx, req); err != nil { return ctrl.Result{}, err }
		}
	}
	return ctrl.Result{RequeueAfter: 60 * time.Second}, nil
}

// reconcileCanary handles canary deployment lifecycle.
func (r *ModelDeploymentReconciler) reconcileCanary(ctx context.Context, md *v1alpha1.ModelDeployment, eng string, platform *v1alpha1.LLMPlatform) error {
	log := logf.FromContext(ctx)
	canary := md.Spec.Canary
	canarySlug := builder.CanarySlug(canary.Source)

	// Canary PVC
	canaryPVC := builder.BuildCanaryPVC(md, canarySlug)
	if canaryPVC != nil {
		existing := &corev1.PersistentVolumeClaim{}
		if err := r.Get(ctx, types.NamespacedName{Name: canaryPVC.Name, Namespace: canaryPVC.Namespace}, existing); err != nil {
			if apierrors.IsNotFound(err) {
				if err := controllerutil.SetControllerReference(md, canaryPVC, r.Scheme); err != nil { return err }
				if err := r.Create(ctx, canaryPVC); err != nil { return err }
				log.Info("created canary PVC", "name", canaryPVC.Name)
			}
		}
	}

	// Canary Deployment
	canaryMD := &v1alpha1.ModelDeployment{
		ObjectMeta: metav1.ObjectMeta{Name: md.Name + "-canary", Namespace: md.Namespace},
		Spec: v1alpha1.ModelDeploymentSpec{
			Source: canary.Source, Engine: md.Spec.Engine,
			Replicas: ptr.To(int32(1)), Resources: canary.Resources,
			Accelerator: md.Spec.Accelerator,
		},
	}
	canaryDep := builder.BuildCanaryDeployment(canaryMD, eng, platform, md.Name, canarySlug)
	existingDep := &appsv1.Deployment{}
	if err := r.Get(ctx, types.NamespacedName{Name: canaryDep.Name, Namespace: canaryDep.Namespace}, existingDep); err != nil {
		if apierrors.IsNotFound(err) {
			if err := controllerutil.SetControllerReference(md, canaryDep, r.Scheme); err != nil { return err }
			if err := r.Create(ctx, canaryDep); err != nil { return err }
			log.Info("created canary Deployment", "name", canaryDep.Name)
		}
	} else {
		canaryDep.Spec.Replicas = existingDep.Spec.Replicas
		if !reflect.DeepEqual(existingDep.Spec, canaryDep.Spec) {
			existingDep.Spec = canaryDep.Spec
			if err := r.Update(ctx, existingDep); err != nil { return err }
		}
	}

	// Canary Service
	canarySvc := builder.BuildCanaryService(canaryMD, eng, md.Name)
	existingSvc := &corev1.Service{}
	if err := r.Get(ctx, types.NamespacedName{Name: canarySvc.Name, Namespace: canarySvc.Namespace}, existingSvc); err != nil {
		if apierrors.IsNotFound(err) {
			if err := controllerutil.SetControllerReference(md, canarySvc, r.Scheme); err != nil { return err }
			if err := r.Create(ctx, canarySvc); err != nil { return err }
			log.Info("created canary Service", "name", canarySvc.Name)
		}
	}

	// Canary PDB
	if err := r.ensurePDB(ctx, md, md.Name+"-canary"); err != nil { return err }

	// Update canary status
	canaryDep = &appsv1.Deployment{}
	if err := r.Get(ctx, types.NamespacedName{Name: md.Name + "-canary", Namespace: md.Namespace}, canaryDep); err != nil { return err }
	port := builder.EnginePort(eng)
	md.Status.Canary = &v1alpha1.CanaryStatus{
		Phase:         getCanaryPhase(canaryDep),
		Endpoint:      fmt.Sprintf("http://%s-canary.%s.svc.cluster.local:%d", md.Name, md.Namespace, port),
		ReadyReplicas: canaryDep.Status.ReadyReplicas,
	}
	return nil
}

// reconcileAutoScaling creates/updates HPA or KEDA ScaledObject.
func (r *ModelDeploymentReconciler) reconcileAutoScaling(ctx context.Context, md *v1alpha1.ModelDeployment, eng string) error {
	if md.Spec.AutoScaling == nil || !md.Spec.AutoScaling.Enabled {
		return r.cleanupAutoScaling(ctx, md)
	}
	if md.Spec.AutoScaling.UseKEDA {
		if err:=r.deleteHPA(ctx,md);err!=nil {return err}
		return r.reconcileKEDA(ctx, md)
	}
	if err:=r.deleteScaledObject(ctx,md);err!=nil {return err}
	return r.reconcileHPA(ctx, md)
}

func (r *ModelDeploymentReconciler) reconcileHPA(ctx context.Context, md *v1alpha1.ModelDeployment) error {
	as := md.Spec.AutoScaling
	minR, maxR := int32(1), int32(10)
	if as.MinReplicas != nil {
		minR = *as.MinReplicas
	}
	if as.MaxReplicas != nil {
		maxR = *as.MaxReplicas
	}

	hpa := &autoscalingv2.HorizontalPodAutoscaler{
		ObjectMeta: metav1.ObjectMeta{
			Name: md.Name, Namespace: md.Namespace,
			Labels: map[string]string{
				"app.kubernetes.io/name": "hpa", "kube-llmops/model": md.Name,
			},
		},
		Spec: autoscalingv2.HorizontalPodAutoscalerSpec{
			ScaleTargetRef: autoscalingv2.CrossVersionObjectReference{
				APIVersion: "apps/v1", Kind: "Deployment", Name: md.Name,
			},
			MinReplicas: &minR, MaxReplicas: maxR,
			Metrics:     []autoscalingv2.MetricSpec{},
		},
	}
	if as.ScaleTargetCPUUtilizationPercentage != nil {
		hpa.Spec.Metrics = append(hpa.Spec.Metrics, autoscalingv2.MetricSpec{
			Type: autoscalingv2.ResourceMetricSourceType,
			Resource: &autoscalingv2.ResourceMetricSource{
				Name: corev1.ResourceCPU,
				Target: autoscalingv2.MetricTarget{
					Type:               autoscalingv2.UtilizationMetricType,
					AverageUtilization: as.ScaleTargetCPUUtilizationPercentage,
				},
			},
		})
	}
	if as.ScaleTargetMemoryUtilizationPercentage != nil {
		hpa.Spec.Metrics = append(hpa.Spec.Metrics, autoscalingv2.MetricSpec{
			Type: autoscalingv2.ResourceMetricSourceType,
			Resource: &autoscalingv2.ResourceMetricSource{
				Name: corev1.ResourceMemory,
				Target: autoscalingv2.MetricTarget{
					Type:               autoscalingv2.UtilizationMetricType,
					AverageUtilization: as.ScaleTargetMemoryUtilizationPercentage,
				},
			},
		})
	}

	if len(hpa.Spec.Metrics)==0 {
		cpuDefault:=int32(70)
		hpa.Spec.Metrics=[]autoscalingv2.MetricSpec{{
			Type: autoscalingv2.ResourceMetricSourceType,
			Resource: &autoscalingv2.ResourceMetricSource{
				Name: corev1.ResourceCPU,
				Target: autoscalingv2.MetricTarget{Type:autoscalingv2.UtilizationMetricType,AverageUtilization:&cpuDefault},
			},
		}}
	}
	existing := &autoscalingv2.HorizontalPodAutoscaler{}
	if err := r.Get(ctx, types.NamespacedName{Name: md.Name, Namespace: md.Namespace}, existing); err != nil {
		if apierrors.IsNotFound(err) {
			if err:=controllerutil.SetControllerReference(md,hpa,r.Scheme);err!=nil {return err}
			return r.Create(ctx, hpa)
		}
		return err
	}
	if reflect.DeepEqual(existing.Spec,hpa.Spec) {return nil}
	existing.Spec = hpa.Spec
	return r.Update(ctx, existing)
}

func (r *ModelDeploymentReconciler) reconcileKEDA(ctx context.Context, md *v1alpha1.ModelDeployment) error {
	as := md.Spec.AutoScaling
	minR, maxR := int32(0), int32(10)
	if as.MinReplicas != nil {
		minR = *as.MinReplicas
	}
	if as.MaxReplicas != nil {
		maxR = *as.MaxReplicas
	}

	metricName := "vllm_queue_depth"
	threshold := int64(10)
	if as.KEDATriggers != nil && as.KEDATriggers.QueueDepthMetric != "" {
		metricName = as.KEDATriggers.QueueDepthMetric
	}
	if as.KEDATriggers != nil && as.KEDATriggers.QueueDepthThreshold != nil {
		threshold = int64(*as.KEDATriggers.QueueDepthThreshold)
	}

	so := &unstructured.Unstructured{
		Object: map[string]interface{}{
			"apiVersion": "keda.sh/v1alpha1",
			"kind":       "ScaledObject",
			"metadata": map[string]interface{}{
				"name":      md.Name,
				"namespace": md.Namespace,
				"labels": map[string]string{
					"app.kubernetes.io/name": "scaledobject", "kube-llmops/model": md.Name,
				},
			},
			"spec": map[string]interface{}{
				"scaleTargetRef": map[string]interface{}{"name": md.Name},
				"minReplicaCount": minR,
				"maxReplicaCount": maxR,
				"triggers": []map[string]interface{}{
					{
						"type": "prometheus",
						"name": "queue-depth",
						"metadata": map[string]interface{}{
							"serverAddress": "http://prometheus:9090",
							"metricName":  metricName,
							"threshold":    strconv.FormatInt(threshold, 10),
							"query":       fmt.Sprintf("sum(%s{job=\"vllm\",model=\"%s\"}) or vector(0)", metricName, md.Name),
						},
					},
				},
			},
		},
	}

	existing := &unstructured.Unstructured{}
	existing.SetGroupVersionKind(schema.GroupVersionKind{Group: "keda.sh", Version: "v1alpha1", Kind: "ScaledObject"})
	if err := r.Get(ctx, types.NamespacedName{Name: md.Name, Namespace: md.Namespace}, existing); err != nil {
		if apierrors.IsNotFound(err) {
			if err:=controllerutil.SetControllerReference(md,so,r.Scheme);err!=nil {return err}
			return r.Create(ctx, so)
		}
		return err
	}
	if reflect.DeepEqual(existing.Object["spec"],so.Object["spec"]) {return nil}
	so.SetResourceVersion(existing.GetResourceVersion())
	return r.Update(ctx, so)
}

func (r *ModelDeploymentReconciler) deleteHPA(ctx context.Context, md *v1alpha1.ModelDeployment) error {
	hpa:=&autoscalingv2.HorizontalPodAutoscaler{}
	if err:=r.Get(ctx,types.NamespacedName{Name:md.Name,Namespace:md.Namespace},hpa);err!=nil {
		if apierrors.IsNotFound(err) {return nil}
		return err
	}
	return client.IgnoreNotFound(r.Delete(ctx,hpa))
}

func (r *ModelDeploymentReconciler) deleteScaledObject(ctx context.Context, md *v1alpha1.ModelDeployment) error {
	so:=&unstructured.Unstructured{}
	so.SetGroupVersionKind(schema.GroupVersionKind{Group:"keda.sh",Version:"v1alpha1",Kind:"ScaledObject"})
	if err:=r.Get(ctx,types.NamespacedName{Name:md.Name,Namespace:md.Namespace},so);err!=nil {
		// KEDA is optional: its CRD may legitimately be absent in CPU clusters.
		if apierrors.IsNotFound(err) || apimeta.IsNoMatchError(err) {return nil}
		return err
	}
	return client.IgnoreNotFound(r.Delete(ctx,so))
}

func (r *ModelDeploymentReconciler) cleanupAutoScaling(ctx context.Context, md *v1alpha1.ModelDeployment) error {
	if err:=r.deleteHPA(ctx,md);err!=nil {return err}
	return r.deleteScaledObject(ctx,md)
}

func (r *ModelDeploymentReconciler) ensurePDB(ctx context.Context, md *v1alpha1.ModelDeployment, name string) error {
	maxU := intstr.FromInt(0)
	pdb := &policyv1.PodDisruptionBudget{
		ObjectMeta: metav1.ObjectMeta{
			Name: name, Namespace: md.Namespace,
			Labels: map[string]string{"kube-llmops/model": md.Name},
		},
		Spec: policyv1.PodDisruptionBudgetSpec{
			MaxUnavailable: &maxU,
			Selector: &metav1.LabelSelector{
				MatchLabels: map[string]string{"app.kubernetes.io/instance": name},
			},
		},
	}
	existing := &policyv1.PodDisruptionBudget{}
	if err := r.Get(ctx, types.NamespacedName{Name: name, Namespace: md.Namespace}, existing); err != nil {
		if apierrors.IsNotFound(err) {
			_ = controllerutil.SetControllerReference(md, pdb, r.Scheme)
			return r.Create(ctx, pdb)
		}
		return err
	}
	return nil
}

func (r *ModelDeploymentReconciler) updateStatus(ctx context.Context, req ctrl.Request, md *v1alpha1.ModelDeployment, eng string) error {
	dep := &appsv1.Deployment{}
	if err := r.Get(ctx, types.NamespacedName{Name: md.Name, Namespace: md.Namespace}, dep); err != nil {
		return err
	}

	initStatus, err := r.getInitContainerStatus(ctx, md)
	if err != nil { return err }
	port := builder.EnginePort(eng)
	md.Status.Engine = eng
	md.Status.ReadyReplicas = dep.Status.ReadyReplicas
	md.Status.TotalReplicas = dep.Status.Replicas
	md.Status.Endpoint = fmt.Sprintf("http://%s.%s.svc.cluster.local:%d", md.Name, md.Namespace, port)

	desired := int32(1)
	if md.Spec.Replicas != nil {
		desired = *md.Spec.Replicas
	}

	now := metav1.NewTime(time.Now())
	if initStatus != nil && (initStatus.Phase == "Pending" || initStatus.Phase == "Running") {
		md.Status.Phase = "Downloading"
		md.Status.InitContainerStatus = v1alpha1.InitContainerStatus{Phase: initStatus.Phase, Message: initStatus.Message}
		md.Status.DownloadProgress = &v1alpha1.DownloadProgress{StartTime: &now}
	} else if md.Status.DownloadProgress != nil && md.Status.DownloadProgress.CompletionTime == nil && initStatus != nil && initStatus.Phase == "Terminated" {
		md.Status.DownloadProgress.CompletionTime = &now
	}

	switch {
	case dep.Status.ReadyReplicas >= desired && desired > 0:
		md.Status.Phase = "Ready"
	case dep.Status.ReadyReplicas > 0:
		md.Status.Phase = "Degraded"
	case dep.Status.ReadyReplicas == 0 && desired > 0:
		if md.Status.Phase != "Downloading" {
			md.Status.Phase = "Deploying"
		}
	}

	readyCond := metav1.Condition{Type: "Ready", LastTransitionTime: now, ObservedGeneration: md.Generation}
	if md.Status.Phase == "Ready" {
		readyCond.Status = metav1.ConditionTrue
		readyCond.Reason = "AllReplicasReady"
		readyCond.Message = "All replicas are ready"
	} else if md.Status.Phase == "Downloading" {
		readyCond.Status = metav1.ConditionFalse
		readyCond.Reason = "ModelDownloading"
		readyCond.Message = "Model is being downloaded"
	} else {
		readyCond.Status = metav1.ConditionFalse
		readyCond.Reason = "ReplicasNotReady"
		readyCond.Message = fmt.Sprintf("%d/%d replicas ready", dep.Status.ReadyReplicas, desired)
	}
	setCondition(&md.Status.Conditions, readyCond)

	status := md.Status
	latest := &v1alpha1.ModelDeployment{}
	if err := r.Get(ctx, req.NamespacedName, latest); err != nil { return err }
	if reflect.DeepEqual(latest.Status, status) { return nil }
	latest.Status = status
	return r.Status().Update(ctx, latest)
}

// PodStatus, not DeploymentStatus, owns per-init-container lifecycle states.
func (r *ModelDeploymentReconciler) getInitContainerStatus(ctx context.Context, md *v1alpha1.ModelDeployment) (*v1alpha1.InitContainerStatus, error) {
	pods := &corev1.PodList{}
	if err := r.List(ctx, pods, client.InNamespace(md.Namespace), client.MatchingLabels{"kube-llmops/model": md.Name}); err != nil {
		return nil, err
	}
	for _, pod := range pods.Items {
		for _, cs := range pod.Status.InitContainerStatuses {
			if cs.Name != "model-loader" { continue }
			status := &v1alpha1.InitContainerStatus{}
			switch {
			case cs.State.Running != nil:
				status.Phase, status.Message = "Running", "Model download in progress"
			case cs.State.Terminated != nil:
				status.Phase = "Terminated"
				if cs.State.Terminated.ExitCode == 0 {
					status.Message = "Model download completed"
				} else {
					status.Message = fmt.Sprintf("Model download failed: %s", cs.State.Terminated.Reason)
				}
			case cs.State.Waiting != nil:
				status.Phase, status.Message = "Pending", cs.State.Waiting.Reason
			default:
				status.Phase = "Pending"
			}
			return status, nil
		}
	}
	return nil, nil
}

func (r *ModelDeploymentReconciler) registerWithGateway(ctx context.Context, md *v1alpha1.ModelDeployment, eng string) error {
	modelType := engine.ResolveModelType(md.Spec.Source)
	prefix := "openai/"
	apiBase := md.Status.Endpoint
	if modelType == "embedding" || modelType == "reranker" {
		prefix = "huggingface/"
		apiBase = strings.TrimSuffix(apiBase, "/v1")
	}

	model := gateway.GatewayModel{
		ModelName: md.Name,
		LiteLLMParams: gateway.LiteLLMParams{
			Model: prefix + md.Name, APIBase: apiBase,
		},
	}
	if err := r.GatewayClient.RegisterModel(ctx, model); err != nil {
		return fmt.Errorf("register model: %w", err)
	}

	if md.Spec.Canary != nil && md.Status.Canary != nil && md.Status.Canary.Phase == "Ready" && md.Spec.Canary.Weight > 0 {
		canaryModel := gateway.GatewayModel{
			ModelName: md.Name + "-canary",
			LiteLLMParams: gateway.LiteLLMParams{
				Model:   prefix + md.Name,
				APIBase: md.Status.Canary.Endpoint,
				Weight: ptr.To(int(md.Spec.Canary.Weight)),
			},
		}
		if err := r.GatewayClient.RegisterModel(ctx, canaryModel); err != nil {
			return fmt.Errorf("register canary: %w", err)
		}
	}
	return nil
}

// Never report a model Ready if the route through LiteLLM failed.
func (r *ModelDeploymentReconciler) setGatewayDegraded(ctx context.Context, req ctrl.Request, reason string) (ctrl.Result, error) {
	latest := &v1alpha1.ModelDeployment{}
	if err := r.Get(ctx, req.NamespacedName, latest); err != nil { return ctrl.Result{}, err }
	latest.Status.Phase = "Degraded"
	setCondition(&latest.Status.Conditions, metav1.Condition{
		Type: "GatewayReady", Status: metav1.ConditionFalse,
		Reason: reason, Message: "Serving pods ready but gateway route is unavailable",
		LastTransitionTime: metav1.Now(), ObservedGeneration: latest.Generation,
	})
	setCondition(&latest.Status.Conditions, metav1.Condition{
		Type: "Ready", Status: metav1.ConditionFalse,
		Reason: reason, Message: "Gateway registration is required before model readiness",
		LastTransitionTime: metav1.Now(), ObservedGeneration: latest.Generation,
	})
	if err := r.Status().Update(ctx, latest); err != nil { return ctrl.Result{}, err }
	return ctrl.Result{RequeueAfter: 20 * time.Second}, nil
}

// gatewayConditionUpToDate requires that the current CR generation has already
// been registered with the gateway; older successes cannot certify new weights.
func gatewayConditionUpToDate(md *v1alpha1.ModelDeployment) bool {
	for _,cond:=range md.Status.Conditions {
		if cond.Type=="GatewayReady" && cond.Status==metav1.ConditionTrue &&
			cond.ObservedGeneration>=md.Generation { return true }
	}
	return false
}

func (r *ModelDeploymentReconciler) setGatewayReady(ctx context.Context, req ctrl.Request) error {
	latest := &v1alpha1.ModelDeployment{}
	if err := r.Get(ctx, req.NamespacedName, latest); err != nil { return err }
	setCondition(&latest.Status.Conditions, metav1.Condition{
		Type: "GatewayReady", Status: metav1.ConditionTrue,
		Reason: "Registered", Message: "Gateway accepted model registration",
		LastTransitionTime: metav1.Now(), ObservedGeneration: latest.Generation,
	})
	return r.Status().Update(ctx, latest)
}

func getCanaryPhase(dep *appsv1.Deployment) string {
	if dep.Spec.Replicas != nil && *dep.Spec.Replicas > 0 &&
		dep.Status.ObservedGeneration >= dep.Generation &&
		dep.Status.ReadyReplicas >= *dep.Spec.Replicas {
		return "Ready"
	}
	if dep.Status.Replicas > 0 {
		return "Deploying"
	}
	return "Pending"
}

func setCondition(conditions *[]metav1.Condition, cond metav1.Condition) {
	for i, current := range *conditions {
		if current.Type == cond.Type {
			// Conditions must not be churned on every reconcile. Preserve the
			// transition time when the externally observable state is unchanged.
			if current.Status == cond.Status && current.Reason == cond.Reason &&
				current.Message == cond.Message {
				cond.LastTransitionTime = current.LastTransitionTime
			}
			(*conditions)[i] = cond
			return
		}
	}
	*conditions = append(*conditions, cond)
}

func (r *ModelDeploymentReconciler) SetupWithManager(mgr ctrl.Manager) error {
	return ctrl.NewControllerManagedBy(mgr).
		For(&v1alpha1.ModelDeployment{}).
		Owns(&appsv1.Deployment{}).
		Owns(&corev1.Service{}).
		Owns(&corev1.PersistentVolumeClaim{}).
		Owns(&autoscalingv2.HorizontalPodAutoscaler{}).
		Named("modeldeployment").
		Complete(r)
}
