# Roda todos os testes: N (1..5) x cenarios (3) x cargas (min, med, max) = 45 execucoes.
# Precisa do cargas.json gerado pelo achar_limite.ps1.
# Pode ser interrompido e rodado de novo: pula o que ja esta no resumo.csv.
#
# Uso:  .\rodar_testes.ps1
#       .\rodar_testes.ps1 -Maquina PC-JEAN -Duracao 60 -Ns 1,2,3,4,5
param(
    [string]$Maquina = $env:COMPUTERNAME,
    [int[]]$Ns = @(1, 2, 3, 4, 5),
    [int]$Duracao = 60,
    [int]$Pausa = 15
)
. "$PSScriptRoot\lib.ps1"

$pasta = Join-Path $PastaResultados $Maquina
$cargasPath = Join-Path $pasta "cargas.json"
if (-not (Test-Path $cargasPath)) { throw "Rode primeiro: .\achar_limite.ps1 -Maquina $Maquina" }
$cargas = Get-Content $cargasPath -Raw | ConvertFrom-Json
$resumo = Join-Path $pasta "resumo.csv"
$ci = [Globalization.CultureInfo]::InvariantCulture

if (-not (Test-Path $resumo)) {
    Set-Content $resumo "maquina,n,cenario,carga,usuarios,requests,falhas,erro_pct,media_ms,mediana_ms,p95_ms,rps,valido" -Encoding ASCII
}

# O que ja foi feito (para retomar)
$feitos = @{}
Import-Csv $resumo -Delimiter "," | ForEach-Object { $feitos["$($_.n)|$($_.cenario)|$($_.carga)"] = $true }

$niveis = @("min", "med", "max")

foreach ($n in $Ns) {
    $pendente = $false
    foreach ($c in $cargas.cenarios) {
        foreach ($nivel in $niveis) {
            if (-not $feitos["$n|$($c.id)|$nivel"]) { $pendente = $true }
        }
    }
    if (-not $pendente) { Write-Host "N=$n ja concluido, pulando." -ForegroundColor DarkGray; continue }

    Start-Cluster $n

    foreach ($c in $cargas.cenarios) {
        foreach ($nivel in $niveis) {
            if ($feitos["$n|$($c.id)|$nivel"]) { continue }
            $usuarios = [int]$c.$nivel
            Write-Host "`n--- N=$n | cenario $($c.id) ($($c.nome)) | carga $nivel = $usuarios usuarios ---" -ForegroundColor Cyan
            $r = Invoke-Teste -Post $c.post -Usuarios $usuarios -Duracao $Duracao -Prefixo "$Maquina\N${n}_c$($c.id)_$nivel"

            if ($nivel -eq "max") { $valido = ($r.ErroPct -le 10) } else { $valido = ($r.ErroPct -eq 0) }
            $txtValido = "nao"; if ($valido) { $txtValido = "sim" }
            if (-not $valido) {
                Write-Warning ("Regra do professor violada: erro {0:N2}% na carga {1}. Considere recalibrar (achar_limite.ps1 -N {2})." -f $r.ErroPct, $nivel, $n)
            }
            Write-Host ("  erro {0:N2}% | media {1:N0} ms | p95 {2:N0} ms | {3:N1} req/s" -f $r.ErroPct, $r.MediaMs, $r.P95Ms, $r.Rps)

            $campos = @(
                $Maquina, $n, $c.id, $nivel, $usuarios,
                $r.Requests.ToString("0", $ci), $r.Falhas.ToString("0", $ci),
                $r.ErroPct.ToString("0.00", $ci), $r.MediaMs.ToString("0.0", $ci),
                $r.MedianaMs.ToString("0.0", $ci), $r.P95Ms.ToString("0.0", $ci),
                $r.Rps.ToString("0.00", $ci), $txtValido
            )
            Add-Content $resumo ($campos -join ",") -Encoding ASCII
            $feitos["$n|$($c.id)|$nivel"] = $true
            Start-Sleep $Pausa
        }
    }
}

docker compose down 2>&1 | Out-Null
Write-Host "`nConcluido. Resumo: $resumo" -ForegroundColor Green
