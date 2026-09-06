param(
    [ValidateSet("start", "stop")][string]$Action = "start",
    [string]$PgBin = "C:\Program Files\PostgreSQL\17\bin",
    [int]$Port = 55432
)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$clusterPath = Join-Path $repoRoot ".local/pgdata"
$logPath = Join-Path $repoRoot ".local/postgres.log"
if (-not (Test-Path (Join-Path $PgBin "pg_ctl.exe"))) { throw "PostgreSQL binaries not found: $PgBin" }
if ($Action -eq "stop") {
    & "$PgBin/pg_ctl.exe" -D $clusterPath -m fast -w stop
    exit $LASTEXITCODE
}
if (-not (Test-Path (Join-Path $clusterPath "PG_VERSION"))) {
    New-Item -ItemType Directory -Force (Split-Path $clusterPath -Parent) | Out-Null
    & "$PgBin/initdb.exe" -D $clusterPath -U lab --auth=trust --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw "initdb failed" }
}
& "$PgBin/pg_ctl.exe" -D $clusterPath status *> $null
if ($LASTEXITCODE -ne 0) {
    & "$PgBin/pg_ctl.exe" -D $clusterPath -l $logPath -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL startup failed" }
}
foreach ($dbName in @("lab_platform_p02", "lab_platform_p02_test")) {
    $exists = & "$PgBin/psql.exe" -h 127.0.0.1 -p $Port -U lab -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbName'"
    if ($LASTEXITCODE -ne 0) { throw "Cannot connect to isolated PostgreSQL cluster" }
    if ($exists -ne "1") {
        & "$PgBin/createdb.exe" -h 127.0.0.1 -p $Port -U lab $dbName
        if ($LASTEXITCODE -ne 0) { throw "Database creation failed" }
    }
}
Write-Output "Local development cluster ready on 127.0.0.1:$Port (trust authentication; never expose externally)."
