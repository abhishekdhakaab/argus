resource "google_storage_bucket" "raw_documents" {
  name                        = "${var.project_id}-argus-raw-documents"
  location                    = var.region
  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.required]
}
