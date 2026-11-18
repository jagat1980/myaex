<#
.SYNOPSIS
    Wrapper script to safely execute Terraform commands while injecting environment
    variables (such as github_pat) from the local .env file.

.DESCRIPTION
    Reads .env located at the project root and sets GITHUB_TOKEN and TF_VAR_github_token
    in the current process environment before invoking Terraform in infra/terraform.

.EXAMPLE
    .\scripts\run_terraform.ps1 plan
    .\scripts\run_terraform.ps1 apply
#>

[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$TerraformArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$EnvFile = Join-Path $ProjectRoot ".env"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and ($line -match '^\s*([^#=\s]+)\s*=\s*(.*)$')) {
            $name = $matches[1]
            $val = $matches[2]
            [System.Environment]::SetEnvironmentVariable($name, $val, "Process")
        }
    }
}

if ($env:github_pat) {
    $env:GITHUB_TOKEN = $env:github_pat
    $env:TF_VAR_github_token = $env:github_pat
}

$TfDir = Join-Path $ProjectRoot "infra\terraform"

if (-not $TerraformArgs) {
    terraform -chdir="$TfDir" --help
} else {
    terraform -chdir="$TfDir" @TerraformArgs
}
