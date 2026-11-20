$ErrorActionPreference = 'Stop'

$image = 'hashicorp/terraform:1.15.9'
$source = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$volume = 'folio-terraform-check-' + [Guid]::NewGuid().ToString('N')
$sourceMount = "type=bind,source=$source,target=/source,readonly"
$checkMount = "type=volume,source=$volume,target=/check"
$offlineArgs = @(
    'run', '--rm', '--pull', 'never', '--network', 'none',
    '--mount', $sourceMount, '--mount', $checkMount, '-w', '/check',
    '--env', 'CHECKPOINT_DISABLE=1', '--env', 'TF_IN_AUTOMATION=1',
    '--env', 'AWS_ACCESS_KEY_ID=offline', '--env', 'AWS_SECRET_ACCESS_KEY=offline',
    '--env', 'AWS_EC2_METADATA_DISABLED=true'
)

function Assert-Plan([bool] $condition, [string] $message) {
    if (-not $condition) { throw $message }
}

docker volume create $volume | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Could not create the temporary Docker volume.' }

try {
    # Init downloads the public provider plugin. The repository is mounted read-only.
    $initialize = @'
cp /source/main.tf /source/providers.tf /source/variables.tf /source/outputs.tf /source/.terraform.lock.hcl .
cp -R /source/modules .
terraform init -backend=false -input=false -lockfile=readonly -no-color
'@
    docker run --rm --mount $sourceMount --mount $checkMount -w /check `
        --env CHECKPOINT_DISABLE=1 --env TF_IN_AUTOMATION=1 `
        --entrypoint /bin/sh $image -ec $initialize
    if ($LASTEXITCODE -ne 0) { throw 'Terraform init failed.' }

    # Validate the cloud configuration first, then add the offline provider override.
    # Docker disables networking during both commands. No local credentials or state
    # are copied into the verification volume.
    $verify = @'
terraform fmt -check -recursive -no-color /source
terraform validate -no-color
cp /source/examples/offline-provider.tf.example ./local_override.tf
terraform plan -input=false -refresh=false -no-color -var-file=/source/examples/offline.tfvars -out=folio.tfplan
if terraform plan -input=false -refresh=false -no-color -var-file=/source/examples/offline.tfvars -var=ssh_source_cidr=0.0.0.0/0 > public-ssh.log 2>&1; then
    echo 'Terraform accepted a public SSH rule.' >&2
    exit 1
fi
if ! grep -Fq 'SSH access requires one administrator IPv4 address' public-ssh.log; then
    cat public-ssh.log >&2
    exit 1
fi
echo 'Terraform rejected the public SSH rule as expected.'
'@
    docker @offlineArgs --entrypoint /bin/sh $image -ec $verify
    if ($LASTEXITCODE -ne 0) { throw 'Terraform validation or offline planning failed.' }

    $json = docker @offlineArgs $image show -json folio.tfplan
    if ($LASTEXITCODE -ne 0) { throw 'Could not inspect the generated Terraform plan.' }
    $plan = ($json -join "`n") | ConvertFrom-Json
    $changes = @($plan.resource_changes)
    $nonCreates = @($changes | Where-Object { ($_.change.actions -join ',') -ne 'create' })
    $vm = $changes | Where-Object address -eq 'aws_instance.folio'
    $disk = $changes | Where-Object address -eq 'aws_ebs_volume.data'
    $attachment = $changes | Where-Object address -eq 'aws_volume_attachment.data'
    $ingress = @($changes | Where-Object type -eq 'aws_vpc_security_group_ingress_rule')
    Assert-Plan ($changes.Count -eq 13 -and $nonCreates.Count -eq 0) 'Expected 13 new resources and no updates or deletions.'
    Assert-Plan ($vm.change.after.root_block_device[0].encrypted -eq $true) 'The OS disk must be encrypted.'
    Assert-Plan ($vm.change.after.metadata_options[0].http_tokens -eq 'required') 'The VM must require IMDSv2.'
    Assert-Plan ($disk.change.after.encrypted -eq $true -and $null -ne $attachment) 'Expected an encrypted, separately attached data disk.'
    Assert-Plan ($ingress.Count -eq 1 -and $ingress[0].change.after.from_port -eq 22 -and `
        $ingress[0].change.after.to_port -eq 22 -and $ingress[0].change.after.ip_protocol -eq 'tcp' -and `
        $ingress[0].change.after.cidr_ipv4 -eq '192.0.2.10/32') 'Only the example administrator may reach SSH.'
    Assert-Plan (@($plan.output_changes.PSObject.Properties.Name).Count -eq 4) 'Expected four infrastructure outputs.'

    Write-Output 'Verified 13 planned resources, encrypted disks, IMDSv2, administrator-only SSH, and four outputs. No cloud resources created.'
} finally {
    docker volume rm $volume | Out-Null
    if ($LASTEXITCODE -ne 0) { Write-Warning "Could not remove the temporary Docker volume $volume." }
}
