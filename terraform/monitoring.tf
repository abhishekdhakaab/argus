resource "google_project_service" "monitoring" {
  project            = var.project_id
  service            = "monitoring.googleapis.com"
  disable_on_destroy = false
}

resource "google_monitoring_alert_policy" "gateway_high_latency" {
  project      = var.project_id
  display_name = "Argus gateway — high latency (P95 > 5 s)"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run request latency P95 > 5000 ms"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"argus-gateway\" AND metric.type=\"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 5000

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MEAN"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = []

  depends_on = [google_project_service.monitoring]
}

resource "google_monitoring_alert_policy" "gateway_high_error_rate" {
  project      = var.project_id
  display_name = "Argus gateway — high error rate (> 2 %)"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run 5xx response ratio > 0.02"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"argus-gateway\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.02

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = []

  depends_on = [google_project_service.monitoring]
}

resource "google_monitoring_alert_policy" "gateway_zero_traffic" {
  project      = var.project_id
  display_name = "Argus gateway — zero traffic (5 min)"
  combiner     = "OR"

  conditions {
    display_name = "Cloud Run request count drops to 0"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"argus-gateway\" AND metric.type=\"run.googleapis.com/request_count\""
      duration        = "300s"
      comparison      = "COMPARISON_LT"
      threshold_value = 1

      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_RATE"
        cross_series_reducer = "REDUCE_SUM"
        group_by_fields      = ["resource.labels.service_name"]
      }
    }
  }

  notification_channels = []

  depends_on = [google_project_service.monitoring]
}
