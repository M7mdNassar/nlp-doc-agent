variable "project_name" {
  description = "Name used for resource tags and the SSH key name prefix."
  type        = string
  default     = "folio"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,23}$", var.project_name))
    error_message = "Use 3 to 24 lowercase letters, digits or hyphens and start with a letter."
  }
}

variable "aws_region" {
  description = "AWS region for the future deployment."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Standard availability zone in aws_region for the subnet, VM and data disk."
  type        = string

  validation {
    condition     = can(regex("^${var.aws_region}[a-z]$", var.availability_zone))
    error_message = "The availability zone must be a standard zone in aws_region, such as us-east-1a."
  }
}

variable "ami_id" {
  description = "Region-specific Linux image ID compatible with the EC2 instance type."
  type        = string

  validation {
    condition     = can(regex("^ami-[0-9a-f]{17}$", var.ami_id))
    error_message = "Provide a Linux AMI ID with ami- followed by 17 lowercase hexadecimal characters."
  }
}

variable "instance_type" {
  description = "EC2 instance size. Use a CPU instance for the baseline or explicitly choose one with a supported GPU."
  type        = string
  default     = "m7i.xlarge"
}

variable "vpc_cidr" {
  description = "IPv4 range for the dedicated virtual network. The module derives one subnet from it."
  type        = string
  default     = "10.42.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr)) && can(regex("/(1[6-9]|20)$", var.vpc_cidr))
    error_message = "Provide an IPv4 CIDR with a prefix from /16 to /20."
  }
}

variable "ssh_source_cidr" {
  description = "Public IPv4 address of the administrator as a /32 CIDR, for SSH access."
  type        = string

  validation {
    condition     = can(cidrnetmask(var.ssh_source_cidr)) && endswith(var.ssh_source_cidr, "/32")
    error_message = "SSH access requires one administrator IPv4 address with a /32 prefix."
  }
}

variable "ssh_public_key" {
  description = "Administrator's public OpenSSH key. The private key stays with the administrator."
  type        = string

  validation {
    condition     = can(regex("^ssh-(ed25519|rsa) [A-Za-z0-9+/=]+( [^\n\r]+)?$", var.ssh_public_key))
    error_message = "Provide a single-line OpenSSH public key starting with ssh-ed25519 or ssh-rsa."
  }
}

variable "root_volume_gib" {
  description = "Size of the encrypted OS disk in GiB."
  type        = number
  default     = 30

  validation {
    condition     = var.root_volume_gib >= 20 && var.root_volume_gib <= 16384 && floor(var.root_volume_gib) == var.root_volume_gib
    error_message = "Use a whole number from 20 to 16384 GiB for the OS disk."
  }
}

variable "data_volume_gib" {
  description = "Size of the separate encrypted disk for Docker volumes, uploads and the model cache."
  type        = number
  default     = 80

  validation {
    condition     = var.data_volume_gib >= 20 && var.data_volume_gib <= 16384 && floor(var.data_volume_gib) == var.data_volume_gib
    error_message = "Use a whole number from 20 to 16384 GiB for the data disk."
  }
}
