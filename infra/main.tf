locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repo_id}/bot:${var.image_tag}"
}

# ---------------------------------------------------------------------------
# Enable required APIs
# ---------------------------------------------------------------------------
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Artifact Registry (Docker) for the bot image
# ---------------------------------------------------------------------------
resource "google_artifact_registry_repository" "bots" {
  location      = var.region
  repository_id = var.repo_id
  format        = "DOCKER"
  description   = "Voice bot container images"
  depends_on    = [google_project_service.services]
}

# ---------------------------------------------------------------------------
# Secrets for the three provider API keys
# ---------------------------------------------------------------------------
resource "google_secret_manager_secret" "keys" {
  for_each = {
    DEEPGRAM_API_KEY = var.deepgram_api_key
    NVIDIA_API_KEY   = var.nvidia_api_key
  }
  secret_id = lower(replace(each.key, "_", "-"))
  replication {
    auto {}
  }
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "keys" {
  for_each = {
    DEEPGRAM_API_KEY = var.deepgram_api_key
    NVIDIA_API_KEY   = var.nvidia_api_key
  }
  secret      = google_secret_manager_secret.keys[each.key].id
  secret_data = each.value
}

# ---------------------------------------------------------------------------
# Runtime service account (least privilege: read its own secrets only)
# ---------------------------------------------------------------------------
resource "google_service_account" "bot" {
  account_id   = "${var.service_name}-sa"
  display_name = "Voice bot runtime SA"
}

resource "google_secret_manager_secret_iam_member" "bot_access" {
  for_each  = google_secret_manager_secret.keys
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.bot.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run v2 service
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service" "bot" {
  name                = var.service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.bot.email

    # concurrency = 1 is the whole "one container = one conversation" rule.
    max_instance_request_concurrency = 1
    timeout                          = "${var.request_timeout_seconds}s"

    scaling {
      min_instance_count = var.min_instances # warm spare pool
      max_instance_count = var.max_instances
    }

    containers {
      image = local.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = var.cpu
          memory = var.memory
        }
        cpu_idle          = var.cpu_idle          # cheap warm spares
        startup_cpu_boost = var.startup_cpu_boost # faster cold import
      }

      env {
        name  = "PIPECAT_WEBSOCKET_AUTH"
        value = "none"
      }

      env {
        name  = "GREETING_MODE"
        value = "llm"
      }

      env {
        name  = "NVIDIA_MODEL"
        value = "meta/llama-3.1-8b-instruct"
      }

      env {
        name  = "NVIDIA_BASE_URL"
        value = "https://integrate.api.nvidia.com/v1"
      }

      dynamic "env" {
        for_each = google_secret_manager_secret.keys
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value.secret_id
              version = "latest"
            }
          }
        }
      }

      # Let Cloud Run use its default startup timeout (~240s). The bot binds
      # PORT only after ~15s of imports; startup_cpu_boost helps.
    }
  }

  depends_on = [
    google_secret_manager_secret_version.keys,
    google_secret_manager_secret_iam_member.bot_access,
  ]
}

# ---------------------------------------------------------------------------
# Public invocation (so the harness can connect over WSS without auth tokens)
# ---------------------------------------------------------------------------
resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.allow_unauthenticated ? 1 : 0
  name     = google_cloud_run_v2_service.bot.name
  location = google_cloud_run_v2_service.bot.location
  role     = "roles/run.invoker"
  member   = "allUsers"
}
