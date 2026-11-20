output "instance_id" {
  description = "EC2 instance ID."
  value       = aws_instance.folio.id
}

output "public_ip" {
  description = "Current IPv4 address for the administrator's SSH connection."
  value       = aws_instance.folio.public_ip
}

output "security_group_id" {
  description = "ID of the firewall group controlling access to the instance."
  value       = module.network.security_group_id
}

output "data_volume_id" {
  description = "EBS volume ID to identify the application data disk on the host."
  value       = aws_ebs_volume.data.id
}
