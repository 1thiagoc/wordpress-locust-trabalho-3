# Descobre, para esta maquina, a carga maxima (erro <= 10%) de cada cenario
# e define a carga minima e a media (ambas com 0% de erro).
#
# Uso:  .\achar_limite.ps1                       (calibra com N=1, 30 s por degrau)
#       .\achar_limite.ps1 -Maquina PC-JEAN -N 1 -Duracao 30
#
# Calibrar com N=1 usa a configuracao mais fraca; assim as cargas nao estouram
# o limite em nenhum N. Se N=5 der erro nesta maquina, recalibre com -N 5.
param(
    [string]$Maquina = $env:COMPUTERNAME,
    [int]$N = 1,
    [int]$Duracao = 30
)
. "$PSScriptRoot\lib.ps1"

$degraus = @(5, 10, 20, 40, 80, 120, 160, 240, 320, 480, 640, 960, 1280)

# Reduz a carga em 25% ate obter 0% de erro (maximo 5 tentativas).
function Garantir-ZeroErro {
    param($Cenario, [int]$Usuarios, [string]$Nome)
    for ($t = 1; $t -le 5; $t++) {
        $r = Invoke-Teste -Post $Cenario.Post -Usuarios $Usuarios -Duracao $Duracao -Prefixo "$Maquina\calibracao\N${N}_c$($Cenario.Id)_${Nome}_u$Usuarios"
        Write-Host ("  {0}: {1} usuarios -> erro {2:N2}%" -f $Nome, $Usuarios, $r.ErroPct)
        if ($r.ErroPct -eq 0) { return $Usuarios }
        $Usuarios = [Math]::Max(1, [int][Math]::Floor($Usuarios * 0.75))
        Start-Sleep 5
    }
    Write-Warning "Nao foi possivel chegar a 0% de erro para a carga $Nome do cenario $($Cenario.Id). Revise manualmente."
    return $Usuarios
}

Start-Cluster $N
$saida = @()

foreach ($c in $Cenarios) {
    Write-Host "`n=== Cenario $($c.Id): $($c.Nome) (post $($c.Post)) ===" -ForegroundColor Cyan
    $bom = 0
    $ruim = 0
    foreach ($u in $degraus) {
        $r = Invoke-Teste -Post $c.Post -Usuarios $u -Duracao $Duracao -Prefixo "$Maquina\calibracao\N${N}_c$($c.Id)_u$u"
        Write-Host ("  {0,5} usuarios -> erro {1:N2}% | media {2:N0} ms | {3:N1} req/s" -f $u, $r.ErroPct, $r.MediaMs, $r.Rps)
        if ($r.ErroPct -le 10) { $bom = $u } else { $ruim = $u; break }
        Start-Sleep 5
    }
    if ($bom -eq 0) { throw "Ja com $($degraus[0]) usuarios o erro passou de 10% no cenario $($c.Id). Verifique se o site esta saudavel." }
    if ($ruim -eq 0) { Write-Warning "O limite nao foi atingido ate $bom usuarios; use mais degraus se quiser achar o limite real." }

    # Refinamento: testa o ponto medio entre o ultimo bom e o primeiro ruim
    if ($ruim -gt 0) {
        $meio = [int][Math]::Round(($bom + $ruim) / 2)
        if ($meio -gt $bom -and $meio -lt $ruim) {
            $r = Invoke-Teste -Post $c.Post -Usuarios $meio -Duracao $Duracao -Prefixo "$Maquina\calibracao\N${N}_c$($c.Id)_u$meio"
            Write-Host ("  {0,5} usuarios -> erro {1:N2}% (refinamento)" -f $meio, $r.ErroPct)
            if ($r.ErroPct -le 10) { $bom = $meio }
        }
    }
    $max = $bom
    Write-Host "  Carga maxima: $max usuarios" -ForegroundColor Green

    $min = Garantir-ZeroErro $c ([Math]::Max(1, [int][Math]::Round($max * 0.2))) "min"
    $med = Garantir-ZeroErro $c ([Math]::Max($min + 1, [int][Math]::Round($max * 0.5))) "med"
    if ($med -le $min -or $max -le $med) { Write-Warning "As cargas ficaram muito proximas (min=$min, med=$med, max=$max). Revise manualmente." }

    $saida += [pscustomobject]@{ id = $c.Id; nome = $c.Nome; post = $c.Post; min = $min; med = $med; max = $max }
}

$pasta = Join-Path $PastaResultados $Maquina
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
[pscustomobject]@{ maquina = $Maquina; n_calibracao = $N; cenarios = $saida } |
    ConvertTo-Json -Depth 5 | Set-Content (Join-Path $pasta "cargas.json") -Encoding UTF8

Write-Host "`nCargas salvas em locust\resultados\$Maquina\cargas.json" -ForegroundColor Green
$saida | Format-Table id, nome, min, med, max -AutoSize
docker compose down 2>&1 | Out-Null
