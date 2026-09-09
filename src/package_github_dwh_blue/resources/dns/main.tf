terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
  }
}
provider "cloudflare" {}

data "cloudflare_zone" "control" {
  filter = { name = "<{ control-plane-zone }>" }
}
resource "cloudflare_dns_record" "control" {
  zone_id = data.cloudflare_zone.control.id
  name    = "<{ control-plane-host }>"
  content = "<{ server-ip }>"
  type    = "A"
  ttl     = 1
  proxied = true
}
resource "cloudflare_dns_record" "analytics" {
  zone_id = data.cloudflare_zone.control.id
  name    = "<{ analytics-host }>"
  content = "<{ server-ip }>"
  type    = "A"
  ttl     = 1
  # Cloudflare Universal SSL does not cover this two-label subdomain.
  proxied = false
}
