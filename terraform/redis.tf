resource "google_vpc_access_connector" "argus" {
  name          = "argus-vpc"
  region        = var.region
  network       = "default"
  ip_cidr_range = "10.8.0.0/28"

  depends_on = [google_project_service.required]
}

resource "google_redis_instance" "argus" {
  name           = "argus-redis"
  tier           = "BASIC"
  memory_size_gb = 1
  region         = var.region
  redis_version  = "REDIS_7_0"

  depends_on = [google_project_service.required]
}

locals {
  redis_url = "redis://${google_redis_instance.argus.host}:${google_redis_instance.argus.port}/0"
}
