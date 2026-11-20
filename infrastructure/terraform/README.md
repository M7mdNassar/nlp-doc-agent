# Folio infrastructure preparation

Task 6 defines an AWS environment for Folio's existing Docker Compose stack. You can demonstrate the infrastructure plan from Windows with Docker Desktop and public internet access to download Terraform and its provider. The plan runs offline. An AWS account and credentials are only needed for a future deployment.

## Design

| Component | Purpose |
| --- | --- |
| One Linux EC2 instance | Runs the frontend, API, worker, Qdrant, and Redis with Compose. Keeping the API and worker on one host lets them share the current SQLite and upload volumes. |
| VPC, subnet, and internet gateway | Give the instance a dedicated IPv4 network and internet access for package, container, and model downloads and calls to configured providers. |
| Security group and SSH key pair | Allow inbound SSH on TCP 22 from one administrator IPv4 address. Outbound HTTP and HTTPS are allowed. The Compose ports stay bound to loopback on the instance and the administrator can open the UI through an SSH tunnel. |
| Two encrypted `gp3` EBS volumes | The root disk holds the OS. The separate data disk can hold Docker volumes for SQLite, uploads, Qdrant, Redis, and cached models once it is mounted and configured on the host. Terraform protects that disk from accidental destruction with `prevent_destroy`. |

`main.tf` connects compute and storage to `modules/network`. `providers.tf` selects the AWS provider and applies common tags. The lock file records the provider version and checksums. `variables.tf` defines the deployment inputs. `outputs.tf` exposes the instance ID, public IP, security group ID, and data volume ID for handoff.

The defaults size a CPU host for a demo in one availability zone. Real workloads require sizing checks and a backup plan. The public IP is assigned by EC2 and can change after a stop and start.

## Verify locally

From the repository root, with Docker Desktop running Linux containers, run this in PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\infrastructure\terraform\verify.ps1
```

1. `terraform init` downloads the AWS provider from the public registry using the committed lock file. The script uses a temporary Docker volume and reads the Terraform files through a read-only mount.
2. `terraform fmt -check` checks formatting and `terraform validate` checks the deployment configuration with networking disabled.
3. `terraform plan` builds a proposed change set from an empty local state with refresh disabled, fictional inputs in `examples/offline.tfvars`, and a temporary provider override. Docker disables network access for this step. The script checks that Terraform rejects SSH open to all IPv4 addresses. It also inspects the saved plan for the expected resource count, disk encryption, required IMDSv2 tokens, allowed inbound SSH, and outputs. It removes the temporary volume at the end.

Look for `Success! The configuration is valid.`, `Plan: 13 to add, 0 to change, 0 to destroy.`, and the final `Verified 13 planned resources` line. Values such as the public IP appear as `(known after apply)` because AWS assigns them when it creates the resources. This test demonstrates a valid plan. AMI availability, account quotas, cost, operating system setup, and application startup require a separate live deployment test.

## Deployment inputs

| Variable | Default or required value |
| --- | --- |
| `project_name` | `folio` |
| `aws_region` | `us-east-1` |
| `availability_zone` | Required. Choose a standard zone in the selected region. |
| `ami_id` | Required. Choose a Linux AMI available in the region and compatible with the instance type. |
| `instance_type` | `m7i.xlarge` (CPU). |
| `vpc_cidr` | `10.42.0.0/16`. The module derives one subnet from this CIDR. |
| `ssh_source_cidr` | Required. Set the administrator's public IPv4 address with `/32`. |
| `ssh_public_key` | Required. Supply an OpenSSH public key. Keep the private key on the administrator's machine. |
| `root_volume_gib` | `30` |
| `data_volume_gib` | `80` |

## Future deployment handoff

For a separately authorized AWS deployment, use the root Terraform configuration with real input values and AWS credentials configured outside Terraform. The offline example and override are for the assignment check only. Review a plan in the target account before provisioning. Terraform prepares the host, network, and storage. Installing Docker and releasing Folio are separate steps.

1. Identify the attached EBS data disk using the Terraform `data_volume_id` output. AWS calls the requested attachment `/dev/sdf`, and Nitro-based Linux instances expose EBS disks as NVMe devices. Mount the filesystem persistently by UUID, such as at `/srv/folio`.
2. Install Docker Engine and the Compose plugin. Set Docker's `data-root` on the data disk and configure the Docker service to require that mount to prevent writes to the OS disk if the data disk is missing. Restore from a backup if migrating existing data. Copy the repository, configure model-provider credentials in the application's environment file, and follow the [Folio quick start](../../README.md#quick-start) with the base Compose file for the CPU host.
3. Substitute the instance's public IP and the AMI's SSH user in an SSH tunnel. For an Ubuntu AMI, use the following example and open `http://localhost:3000` in your browser while the tunnel runs.

   ```sh
   ssh -N -L 127.0.0.1:3000:127.0.0.1:3000 ubuntu@PUBLIC_IP
   ```

References for [Terraform plan](https://developer.hashicorp.com/terraform/cli/commands/plan) and [EBS volume retention](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/preserving-volumes-on-termination.html).
