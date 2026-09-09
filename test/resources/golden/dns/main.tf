terraform {
  required_providers {
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
  }
}
provider "cloudflare" {}

data "cloudflare_zone" "control" {
  filter = { name = "example.com" }
}
resource "cloudflare_dns_record" "control" {
  zone_id = data.cloudflare_zone.control.id
  name    = "github-dwh.example.com"
  content = "192.0.2.10"
  type    = "A"
  ttl     = 1
  proxied = true
}
resource "cloudflare_dns_record" "analytics" {
  zone_id = data.cloudflare_zone.control.id
  name    = "analytics.github-dwh.example.com"
  content = "192.0.2.10"
  type    = "A"
  ttl     = 1
  # Cloudflare Universal SSL does not cover this two-label subdomain.
  proxied = false
}
