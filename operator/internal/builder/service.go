package builder

import (
	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/util/intstr"

	v1alpha1 "github.com/kube-llmops/operator/api/v1alpha1"
)

// buildLabels returns the standard set of labels for builder resources.
func buildLabels(name, engine string) map[string]string {
	return map[string]string{
		"app.kubernetes.io/name":     engine,
		"app.kubernetes.io/instance": name,
		"app.kubernetes.io/part-of":  "kube-llmops",
		"kube-llmops/model":          name,
		"kube-llmops/engine":         engine,
	}
}

// BuildService creates a ClusterIP Service for a ModelDeployment.
func BuildService(md *v1alpha1.ModelDeployment, engine string) *corev1.Service {
	port := DeploymentPort(md, engine)
	labels := buildLabels(md.Name, engine)

	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      md.Name,
			Namespace: md.Namespace,
			Labels:    labels,
		},
		Spec: corev1.ServiceSpec{
			Type: corev1.ServiceTypeClusterIP,
			Selector: map[string]string{
				"app.kubernetes.io/name": engine,
				"kube-llmops/model":      md.Name,
			},
			Ports: []corev1.ServicePort{
				{
					Name:       "http",
					Port:       port,
					TargetPort: intstr.FromInt32(port),
					Protocol:   corev1.ProtocolTCP,
				},
			},
		},
	}
}

// BuildCanaryService creates a ClusterIP Service for a canary ModelDeployment.
func BuildCanaryService(canaryMD *v1alpha1.ModelDeployment, engine string, mainName string) *corev1.Service {
	port := EnginePort(engine)
	labels := buildLabels(mainName+"-canary", engine)

	return &corev1.Service{
		ObjectMeta: metav1.ObjectMeta{
			Name:      mainName + "-canary",
			Namespace: canaryMD.Namespace,
			Labels:    labels,
		},
		Spec: corev1.ServiceSpec{
			Type: corev1.ServiceTypeClusterIP,
			Selector: map[string]string{
				"app.kubernetes.io/name": engine,
				"kube-llmops/model":      mainName + "-canary",
			},
			Ports: []corev1.ServicePort{
				{
					Name:       "http",
					Port:       port,
					TargetPort: intstr.FromInt32(port),
					Protocol:   corev1.ProtocolTCP,
				},
			},
		},
	}
}
