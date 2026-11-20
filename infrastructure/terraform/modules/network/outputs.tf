output "subnet_id" {
  description = "Subnet where the app VM runs."
  value       = aws_subnet.this.id
}

output "security_group_id" {
  description = "Firewall group for the app VM."
  value       = aws_security_group.instance.id
}
