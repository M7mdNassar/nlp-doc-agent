variable "name" {
  description = "Resource naming prefix."
  type        = string
}

variable "vpc_cidr" {
  description = "IPv4 CIDR for the VPC."
  type        = string
}

variable "availability_zone" {
  description = "Availability zone for the application subnet."
  type        = string
}

variable "ssh_source_cidr" {
  description = "Administrator CIDR permitted to use SSH."
  type        = string
}
