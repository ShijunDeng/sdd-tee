{{/*
Expand the name of the chart.
*/}}
{{- define "agentcube.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "agentcube.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Workload manager resource basename (Service / Deployment).
*/}}
{{- define "agentcube.workloadmanager.name" -}}
{{- printf "%s-workloadmanager" (include "agentcube.fullname" .) }}
{{- end }}

{{/*
Router resource basename.
*/}}
{{- define "agentcube.router.name" -}}
{{- printf "%s-router" (include "agentcube.fullname" .) }}
{{- end }}

{{/*
Workload manager ServiceAccount name (matches RBAC).
*/}}
{{- define "agentcube.workloadmanager.serviceAccountName" -}}
{{- printf "%s-workloadmanager" (include "agentcube.fullname" .) }}
{{- end }}

{{/*
Router ServiceAccount name when RBAC is created by this chart.
*/}}
{{- define "agentcube.router.serviceAccountName" -}}
{{- printf "%s-router" (include "agentcube.fullname" .) }}
{{- end }}

{{/*
Volcano agent scheduler basename.
*/}}
{{- define "agentcube.volcano.scheduler.name" -}}
{{- printf "%s-vc-agent-scheduler" (include "agentcube.fullname" .) }}
{{- end }}

{{/*
Image pull secrets for a pod spec.
*/}}
{{- define "agentcube.imagePullSecrets" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets:
  {{- toYaml . | nindent 2 }}
{{- end }}
{{- end }}
