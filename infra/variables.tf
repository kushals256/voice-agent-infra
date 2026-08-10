variable "project_id" {
  type        = string
  description = "GCP project ID to deploy into."
}

variable "region" {
  type        = string
  description = "Region for Artifact Registry and Cloud Run."
  default     = "us-central1"
}

variable "service_name" {
  type        = string
  description = "Cloud Run service name."
  default     = "voicebot"
}

variable "repo_id" {
  type        = string
  description = "Artifact Registry repository id."
  default     = "bots"
}

variable "image_tag" {
  type        = string
  description = "Container image tag to deploy."
  default     = "latest"
}

variable "cpu" {
  type        = string
  description = "vCPU per instance (Cloud Run format, e.g. \"1\", \"2\")."
  default     = "1"
}

variable "memory" {
  type        = string
  description = "Memory per instance (e.g. \"2Gi\")."
  default     = "2Gi"
}

variable "min_instances" {
  type        = number
  description = "Warm spare pool floor. Set to 20 for burst testing; 0 to scale to zero."
  default     = 0
}

variable "max_instances" {
  type        = number
  description = "Ceiling on instances (GCP default quota: 20 for 1 vCPU in us-central1)."
  default     = 20
}

variable "request_timeout_seconds" {
  type        = number
  description = "Max request (call) duration. Cloud Run max is 3600."
  default     = 3600
}

variable "startup_cpu_boost" {
  type        = bool
  description = "Give extra CPU during startup to shrink the ~20s import cold start."
  default     = true
}

variable "cpu_idle" {
  type        = bool
  description = "Throttle CPU when idle. Set false so cold imports get full CPU during startup."
  default     = false
}

variable "allow_unauthenticated" {
  type        = bool
  description = "Allow public (unauthenticated) invocation so the harness can connect over plain WSS."
  default     = true
}

# --- Secrets: passed in via TF_VAR_* env or a gitignored *.tfvars, never committed. ---
variable "deepgram_api_key" {
  type      = string
  sensitive = true
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = "unused"
  description = "Optional if using Groq instead."
}

variable "nvidia_api_key" {
  type      = string
  sensitive = true
  default   = ""
  description = "NVIDIA NIM API key for Llama (integrate.api.nvidia.com)."
}

variable "groq_api_key" {
  type      = string
  sensitive = true
  default   = ""
  description = "Groq API key for Llama LLM (preferred when OpenAI has no credits)."
}
