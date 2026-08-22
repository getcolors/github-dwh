terraform {
  required_version = ">= 1.8"
  required_providers {
    vultr      = { source = "vultr/vultr", version = "~> 2.0" }
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 5.0" }
  }
}
provider "vultr" {}
provider "cloudflare" {}

resource "vultr_ssh_key" "github_dwh" {
  name    = "github-dwh-test"
  ssh_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGl0aHViZHdoLXBsYWNlaG9sZGVy github-dwh-placeholder"
}

resource "vultr_firewall_group" "github_dwh" {
  description = "github-dwh-test"
}
resource "vultr_firewall_rule" "ssh" {
  firewall_group_id = vultr_firewall_group.github_dwh.id
  protocol          = "tcp"
  ip_type           = "v4"
  subnet            = "0.0.0.0"
  subnet_size       = 0
  port              = "22"
  notes             = "SSH"
}
resource "vultr_firewall_rule" "http" {
  firewall_group_id = vultr_firewall_group.github_dwh.id
  protocol          = "tcp"
  ip_type           = "v4"
  subnet            = "0.0.0.0"
  subnet_size       = 0
  port              = "80"
  notes             = "HTTP"
}
resource "vultr_firewall_rule" "https" {
  firewall_group_id = vultr_firewall_group.github_dwh.id
  protocol          = "tcp"
  ip_type           = "v4"
  subnet            = "0.0.0.0"
  subnet_size       = 0
  port              = "443"
  notes             = "HTTPS"
}

resource "vultr_instance" "github_dwh" {
  label             = "github-dwh-test"
  region            = "ams"
  plan              = "vc2-4c-8gb"
  os_id             = 2284
  ssh_key_ids       = [vultr_ssh_key.github_dwh.id]
  firewall_group_id = vultr_firewall_group.github_dwh.id
  enable_ipv6       = false
  backups           = "enabled"
  backups_schedule {
    type = "daily"
    hour = 3
  }
  lifecycle { prevent_destroy = true }
}

data "cloudflare_zone" "control" {
  filter = { name = "example.com" }
}
resource "cloudflare_dns_record" "control" {
  zone_id = data.cloudflare_zone.control.id
  name    = "github-dwh.example.com"
  content = vultr_instance.github_dwh.main_ip
  type    = "A"
  ttl     = 1
  proxied = true
}

output "infra" {
  value = { ip = vultr_instance.github_dwh.main_ip, host = "github-dwh.example.com" }
}
