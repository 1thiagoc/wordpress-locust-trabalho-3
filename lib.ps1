# Funcoes comuns aos scripts de teste (nao rode este arquivo direto).
Set-Location $PSScriptRoot
$ErrorActionPreference = "Continue"

# Cenarios do trabalho: Id, nome e ID do post no WordPress (?p=ID)
$Cenarios = @(
    @{ Id = 1; Nome = "imagem_1mb";   Post = 5 },
    @{ Id = 2; Nome = "texto_400kb";  Post = 8 },
    @{ Id = 3; Nome = "imagem_300kb"; Post = 10 }
)

$PastaResultados = Join-Path $PSScriptRoot "locust\resultados"

# Retorna o estado do container de um servico Compose.
function Get-ComposeServiceState {
    param([string]$Service)

    $idSaida = docker compose ps -a -q $Service 2>$null
    $id = "$($idSaida | Select-Object -First 1)".Trim()
    if ([string]::IsNullOrWhiteSpace($id)) { return "missing" }

    $estadoSaida = docker inspect --format '{{.State.Status}}' $id 2>$null
    if ($LASTEXITCODE -ne 0) { return "unknown" }
    return "$estadoSaida".Trim()
}

# Aguarda o MySQL aceitar conexoes antes de iniciar o WordPress.
function Wait-MySqlReady {
    param([int]$TimeoutSeconds = 180)

    Write-Host "Aguardando o MySQL ficar pronto..." -ForegroundColor Yellow
    $tentativas = [int][Math]::Ceiling($TimeoutSeconds / 3)
    for ($i = 0; $i -lt $tentativas; $i++) {
        docker compose exec -T mysql mysqladmin ping -h 127.0.0.1 -u root --password=r00t --silent 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "MySQL pronto." -ForegroundColor Green
            return
        }

        $estado = Get-ComposeServiceState "mysql"
        if ($estado -eq "exited" -or $estado -eq "dead") {
            Write-Host "O MySQL encerrou durante a inicializacao. Logs:" -ForegroundColor Red
            docker compose logs --tail 80 mysql
            throw "O container mysql encerrou antes de ficar pronto."
        }
        Start-Sleep -Seconds 3
    }

    Write-Host "O MySQL nao ficou pronto dentro do prazo. Logs:" -ForegroundColor Red
    docker compose logs --tail 80 mysql
    throw "Timeout aguardando o MySQL ficar pronto."
}

# Aguarda o WordPress terminar o entrypoint (incluindo wp-config.php) e iniciar Apache.
# Como todas as instancias compartilham ./wordpress, elas precisam ser iniciadas uma a uma.
function Wait-WordPressReady {
    param([string]$Service, [int]$TimeoutSeconds = 180)

    Write-Host "Aguardando $Service concluir a inicializacao..." -ForegroundColor Yellow
    $tentativas = [int][Math]::Ceiling($TimeoutSeconds / 3)

    # O teste ocorre dentro do container, pois as portas das instancias WordPress nao
    # sao publicadas no host. So considera pronto quando existe wp-config.php e Apache
    # aceita uma conexao TCP local.
    # Use aspas simples nos literais PHP para evitar que o Windows PowerShell remova aspas duplas ao chamar Docker.
    $phpProbe = 'if (!is_file(''/var/www/html/wp-config.php'')) { exit(1); } $s = @fsockopen(''127.0.0.1'', 80); if ($s) { fclose($s); exit(0); } exit(1);'

    for ($i = 0; $i -lt $tentativas; $i++) {
        $estado = Get-ComposeServiceState $Service
        if ($estado -eq "exited" -or $estado -eq "dead") {
            Write-Host "$Service encerrou durante a inicializacao. Logs:" -ForegroundColor Red
            docker compose logs --tail 80 $Service
            throw "O container $Service encerrou durante a inicializacao."
        }

        if ($estado -eq "running") {
            docker compose exec -T $Service php -r $phpProbe 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                # Pequena margem para o Apache terminar de estabilizar antes de iniciar
                # a proxima instancia que compartilha o mesmo diretorio.
                Start-Sleep -Seconds 2
                Write-Host "$Service pronto." -ForegroundColor Green
                return
            }
        }
        Start-Sleep -Seconds 3
    }

    Write-Host "$Service nao ficou pronto dentro do prazo. Estado e logs:" -ForegroundColor Red
    docker compose ps -a
    docker compose logs --tail 80 $Service
    throw "Timeout aguardando $Service ficar pronto."
}

# Derruba tudo e inicia os servicos em sequencia para evitar corridas de inicializacao.
# Todas as instancias WordPress compartilham ./wordpress:/var/www/html; por isso, iniciar
# varias ao mesmo tempo pode causar disputa pela criacao/edicao de wp-config.php.
function Start-Cluster {
    param([int]$N)

    if ($N -lt 1 -or $N -gt 5) { throw "N deve estar entre 1 e 5 (recebido: $N)." }

    Write-Host "`n== Subindo cluster com N=$N ==" -ForegroundColor Cyan
    $env:N = "$N"   # o compose exige N ate para o 'down'
    docker compose down
    if ($LASTEXITCODE -ne 0) { throw "docker compose down falhou (N=$N)" }

    # 1. Inicia o banco e espera ele aceitar conexoes.
    Write-Host "Subindo MySQL..." -ForegroundColor Cyan
    docker compose up -d mysql
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir mysql (N=$N)" }
    Wait-MySqlReady -TimeoutSeconds 180

    # 2. Inicia cada WordPress isoladamente e espera a inicializacao terminar antes
    # de iniciar a proxima instancia que usa o mesmo diretorio compartilhado.
    foreach ($i in (1..$N)) {
        $servico = "wordpress$i"
        Write-Host "Subindo $servico..." -ForegroundColor Cyan
        docker compose up -d $servico
        if ($LASTEXITCODE -ne 0) { throw "Falha ao subir $servico (N=$N)" }
        Wait-WordPressReady -Service $servico -TimeoutSeconds 180
    }

    # 3. Sobe o Nginx apenas quando todas as instancias usadas estiverem prontas.
    Write-Host "Subindo Nginx..." -ForegroundColor Cyan
    docker compose up -d nginx
    if ($LASTEXITCODE -ne 0) { throw "Falha ao subir nginx (N=$N)" }

    # Aguarda a aplicacao responder atraves do Nginx.
    $ok = $false
    for ($i = 0; $i -lt 60; $i++) {
        try {
            $r = Invoke-WebRequest "http://localhost/?p=5" -UseBasicParsing -TimeoutSec 10
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
        Start-Sleep 3
    }
    if (-not $ok) {
        Write-Host "O site nao respondeu pelo Nginx. Estado e logs:" -ForegroundColor Red
        docker compose ps -a
        docker compose logs --tail 80 nginx
        throw "O site nao respondeu em http://localhost apos 3 minutos (N=$N)"
    }

    # Aquecimento: a primeira requisicao ao PHP e sempre mais lenta.
    foreach ($c in $Cenarios) {
        1..3 | ForEach-Object {
            try { Invoke-WebRequest "http://localhost/?p=$($c.Post)" -UseBasicParsing -TimeoutSec 30 | Out-Null } catch { }
        }
    }
    Write-Host "Cluster pronto." -ForegroundColor Green
}

# Le o CSV de estatisticas do Locust (linha "Aggregated").
function Read-Stats {
    param([string]$CsvPath)
    if (-not (Test-Path $CsvPath)) { throw "CSV do Locust nao foi gerado: $CsvPath" }
    # -Delimiter "," e obrigatorio: em Windows pt-BR o padrao do Import-Csv seria ";"
    $linha = Import-Csv $CsvPath -Delimiter "," | Where-Object { $_.Name -eq "Aggregated" } | Select-Object -First 1
    if (-not $linha) { throw "Linha 'Aggregated' nao encontrada em $CsvPath" }
    $req = [double]$linha.'Request Count'
    $fal = [double]$linha.'Failure Count'
    $erro = 100.0
    if ($req -gt 0) { $erro = 100.0 * $fal / $req }
    [pscustomobject]@{
        Requests  = $req
        Falhas    = $fal
        ErroPct   = $erro
        MediaMs   = [double]$linha.'Average Response Time'
        MedianaMs = [double]$linha.'Median Response Time'
        P95Ms     = [double]$linha.'95%'
        Rps       = [double]$linha.'Requests/s'
    }
}

# Roda uma execucao do Locust (headless) no container e devolve as estatisticas.
# O Prefixo e relativo a locust\resultados (ex.: "PC-JEAN\N1_c1_min").
function Invoke-Teste {
    param([int]$Post, [int]$Usuarios, [int]$Duracao, [string]$Prefixo)
    $arq = Join-Path $PastaResultados $Prefixo
    New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($arq)) | Out-Null
    $spawn = [Math]::Max(1, [int][Math]::Ceiling($Usuarios / 5))   # sobe todos os usuarios em ~5 s
    $csvLocust = "/locust/resultados/" + ($Prefixo -replace '\\', '/')
    # O Locust 1.x termina com codigo de saida 1 se houver falhas; por isso o codigo nao e checado.
    docker compose run --rm -T --no-deps -e "POST_ID=$Post" locust `
        -f /locust/locustfile.py --host http://nginx --headless `
        -u $Usuarios -r $spawn -t "${Duracao}s" --csv $csvLocust --only-summary 2>&1 | Out-Null
    Read-Stats ($arq + "_stats.csv")
}
