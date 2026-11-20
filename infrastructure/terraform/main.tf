module "network" {
  source = "./modules/network"

  name              = var.project_name
  availability_zone = var.availability_zone
  vpc_cidr          = var.vpc_cidr
  ssh_source_cidr   = var.ssh_source_cidr
}

resource "aws_key_pair" "admin" {
  key_name_prefix = "${var.project_name}-admin-"
  public_key      = var.ssh_public_key
}

resource "aws_instance" "folio" {
  ami                         = var.ami_id
  instance_type               = var.instance_type
  subnet_id                   = module.network.subnet_id
  vpc_security_group_ids      = [module.network.security_group_id]
  associate_public_ip_address = true
  key_name                    = aws_key_pair.admin.key_name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gib
    encrypted             = true
    delete_on_termination = true
  }

  tags = { Name = var.project_name }
}

resource "aws_ebs_volume" "data" {
  availability_zone = var.availability_zone
  type              = "gp3"
  size              = var.data_volume_gib
  encrypted         = true

  # Keep application data independent of the VM's replacement or termination.
  lifecycle {
    prevent_destroy = true
  }

  tags = { Name = "${var.project_name}-data" }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.folio.id
}
