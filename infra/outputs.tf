output "service_url" {
  description = "Base HTTPS URL of the Cloud Run service."
  value       = google_cloud_run_v2_service.bot.uri
}

output "ws_client_url" {
  description = "WebSocket endpoint to point the harness at."
  value       = "${replace(google_cloud_run_v2_service.bot.uri, "https://", "wss://")}/ws-client"
}

output "image" {
  description = "Fully-qualified image the service deploys."
  value       = local.image
}

output "artifact_registry_repo" {
  description = "Artifact Registry repo path for docker push."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${var.repo_id}"
}
