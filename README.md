# Testes de carga do cluster WordPress com Locust

Documentação do Trabalho 3 de Computação Distribuída. O projeto avalia o desempenho de um cluster WordPress atrás do Nginx, variando o número de instâncias WordPress e a carga gerada pelo Locust.

> **Estado documentado:** na máquina `DESKTOP-5LB6RUD`, as calibrações para `N=1`, `N=2` e `N=3` foram executadas e os arquivos `cargas_N1.json`, `cargas_N2.json` e `cargas_N3.json` foram preservados. A bateria comparativa também foi executada com a primeira versão de `rodar_testes.ps1`, usando os valores comuns presentes em `cargas.json` (32, 80 e 160 usuários para todos os N). A validade dos resultados deve ser confirmada em `resumo.csv`; este README não presume que todas as execuções tenham cumprido os limites de erro.

## 1. Objetivo e escopo

O trabalho mede o comportamento de uma aplicação WordPress conforme variam:

- o número de instâncias WordPress atendidas pelo Nginx;
- a quantidade de usuários virtuais concorrentes gerados pelo Locust;
- o conteúdo acessado em cada um dos três cenários definidos no enunciado.

O escopo atual desta máquina está limitado a **N = 1, 2 e 3 instâncias**. A arquitetura usa um único MySQL, um Nginx como proxy/load balancer e as instâncias WordPress compartilhando os arquivos do site. O contêiner do Locust faz parte do mesmo `docker-compose` e roda na mesma máquina que a aplicação, conforme solicitado pelo professor. Isso significa que o gerador de carga também consome CPU e memória do computador testado.

## 2. Cenários de teste

O `locust/locustfile.py` escolhe o post pelo identificador passado na variável `POST_ID`.

| ID do cenário | Cenário | ID do post WordPress | Conteúdo esperado |
|---|---|---:|---|
| 1 | `imagem_1mb` | 5 | Post com imagem de aproximadamente 1 MB |
| 2 | `texto_400kb` | 8 | Post com texto de aproximadamente 400 KB |
| 3 | `imagem_300kb` | 10 | Post com imagem de aproximadamente 300 KB |

Os três posts foram conferidos como públicos em uma janela anônima. O teste do Locust faz uma requisição à página e tenta baixar até três imagens referenciadas no HTML. Por isso, as estatísticas do Locust contabilizam **requisições HTTP** (páginas e imagens), e não apenas visitas completas a posts.

O usuário virtual espera entre 1 e 2 segundos entre tarefas (`wait_time = between(1, 2)`). O cabeçalho `Host: localhost` é usado para preservar o comportamento esperado do WordPress; o tratamento de redirecionamentos do arquivo corrigido mantém as requisições dentro do caminho do Nginx, em vez de tentar acessar `localhost` dentro do próprio contêiner Locust.

## 3. Arquitetura e arquivos relevantes

- `docker-compose.yml`: define `mysql`, `wordpress1` a `wordpress5`, `nginx` e `locust`.
- `wordpress/`: diretório compartilhado pelos contêineres WordPress e Nginx. Deve conter os arquivos e uploads do site.
- `nginx/nginx-1.conf` a `nginx/nginx-5.conf`: definem quais instâncias WordPress entram no upstream do Nginx. A variável de ambiente `N` seleciona o arquivo usado pelo Compose.
- `locust/locustfile.py`: comportamento dos usuários virtuais.
- `lib.ps1`: funções comuns de inicialização do cluster, execução do Locust e leitura dos CSVs.
- `achar_limite.ps1`: calibra as cargas para um valor de `N` por execução.
- `rodar_testes.ps1`: executa a bateria de testes e grava `resumo.csv`.
- `graficos.py`: reúne os resumos disponíveis e gera os gráficos de barras, quando estiver presente na raiz do projeto.
- `locust/resultados/<NOME-DA-MAQUINA>/`: guarda as calibrações e os resultados daquela máquina.

### Versões e inicialização do cluster

Use a versão funcional de `lib.ps1` que contém `Start-Cluster`, `Wait-MySqlReady` e `Wait-WordPressReady`. Ela inicializa o MySQL, aguarda a prontidão do banco, inicia as instâncias WordPress sequencialmente e só depois sobe o Nginx. Isso é importante porque todas as instâncias compartilham `./wordpress:/var/www/html`; inicializá-las ao mesmo tempo pode causar concorrência durante a criação ou edição de `wp-config.php`.

O `docker compose down` usado pelos scripts **não inclui `-v`**, portanto não remove o volume nomeado `mysql_data`. Não utilize `docker compose down -v` durante este trabalho, pois isso apagaria o volume do banco de dados.

## 4. Requisitos e preparação do ambiente

Na máquina que executará os testes:

1. Windows com PowerShell e Docker Desktop instalado e iniciado, usando contêineres Linux.
2. Docker Compose disponível como `docker compose`.
3. Porta TCP 80 livre no host, pois o Nginx publica `80:80`.
4. Projeto na pasta `C:\Users\Jean\wordpress-cluster` (ou caminho equivalente; os comandos devem ser executados na raiz do projeto).
5. Posts 5, 8 e 10 publicados e acessíveis pelo site.
6. Imagens Docker utilizadas no projeto disponíveis localmente ou baixáveis: `mysql:5.7`, `wordpress:5.4.2-php7.2-apache`, `nginx:1.19.0` e `grubykarol/locust` (Locust 1.2.3).

Abra o PowerShell na pasta do projeto:

```powershell
cd C:\Users\Jean\wordpress-cluster
```

Para comandos `docker compose` manuais, defina `N` antes de executá-los, pois o caminho do arquivo de configuração do Nginx usa essa variável:

```powershell
$env:N = "1"
docker compose ps -a
```

## 5. Calibração das cargas

### 5.1 O que `achar_limite.ps1` faz

A calibração é executada **para uma quantidade de instâncias por vez**, indicada por `-N`. Para cada cenário, o script testa degraus crescentes de usuários por 30 segundos (`5, 10, 20, 40, 80, 120, 160, 240, 320, 480, 640, 960 e 1280`) até encontrar uma carga com mais de 10% de erros ou acabar os degraus. Depois, faz um refinamento no ponto médio entre o último degrau aprovado e o primeiro que excedeu o limite.

A partir do maior ponto aceito encontrado, tenta definir:

- **Mínima (`min`)**: começa em aproximadamente 20% da carga máxima e é reduzida em 25% por tentativa se houver erros, procurando chegar a 0%.
- **Média (`med`)**: começa em aproximadamente 50% da carga máxima (ou acima da mínima) e também é reduzida se necessário para chegar a 0%.
- **Máxima (`max`)**: maior ponto aprovado encontrado no processo de degraus/refinamento, com até 10% de erros. Não representa necessariamente o limite físico exato da aplicação; depende dos degraus testados e da duração da medição.

O script cria resultados de calibração em `locust/resultados/<PC>/calibracao/` e grava os valores encontrados em `locust/resultados/<PC>/cargas.json`. **Esse `cargas.json` é sobrescrito a cada calibração**, por isso copie o arquivo após cada execução para preservar os dados de cada N.

### 5.2 Como repetir as calibrações e preservar os arquivos

Execute cada comando e espere até terminar antes de iniciar o próximo. Após cada execução, copie o arquivo gerado:

```powershell
$pasta = ".\locust\resultados\$env:COMPUTERNAME"

.\achar_limite.ps1 -N 1
Copy-Item "$pasta\cargas.json" "$pasta\cargas_N1.json"

.\achar_limite.ps1 -N 2
Copy-Item "$pasta\cargas.json" "$pasta\cargas_N2.json"

.\achar_limite.ps1 -N 3
Copy-Item "$pasta\cargas.json" "$pasta\cargas_N3.json"
```

As calibrações já foram executadas nesta máquina, então não é necessário repeti-las só para rodar novamente a bateria principal. Os arquivos individuais devem ser mantidos como registro da capacidade observada em cada configuração.

### 5.3 Valores calibrados registrados nesta máquina

| Configuração | Cenário | Mínima | Média | Máxima |
|---|---|---:|---:|---:|
| N=1 | `imagem_1mb` | 96 | 240 | 480 |
| N=1 | `texto_400kb` | 96 | 240 | 480 |
| N=1 | `imagem_300kb` | 96 | 240 | 480 |
| N=2 | `imagem_1mb` | 32 | 80 | 160 |
| N=2 | `texto_400kb` | 32 | 80 | 160 |
| N=2 | `imagem_300kb` | 32 | 80 | 160 |
| N=3 | `imagem_1mb` | 32 | 80 | 160 |
| N=3 | `texto_400kb` | 32 | 80 | 160 |
| N=3 | `imagem_300kb` | 32 | 80 | 160 |

Esses valores foram lidos dos arquivos `cargas_N1.json`, `cargas_N2.json` e `cargas_N3.json` fornecidos durante o trabalho. A diferença entre N=1 e N=2/N=3 reforça a importância de considerar o custo do gerador Locust e a memória/CPU da máquina. Não conclua, apenas com a calibração, que uma arquitetura WordPress é intrinsecamente melhor: o resultado mede o conjunto da aplicação e do gerador no mesmo host.

## 6. Bateria comparativa de testes

### 6.1 Qual arquivo de carga foi usado

A **primeira versão** de `rodar_testes.ps1` lê somente `locust/resultados/<PC>/cargas.json` e utiliza os valores desse arquivo para todos os valores de `N` passados no comando. Na execução comparativa já realizada, o arquivo ativo continha os valores abaixo, originados da calibração de N=3:

| Cenário | Carga mínima | Carga média | Carga máxima |
|---|---:|---:|---:|
| `imagem_1mb` | 32 | 80 | 160 |
| `texto_400kb` | 32 | 80 | 160 |
| `imagem_300kb` | 32 | 80 | 160 |

Portanto, a bateria principal executada com a primeira versão usou **os mesmos níveis de carga em N=1, N=2 e N=3**. Isso é intencional para a comparação controlada: mantém o número de usuários constante e permite observar como as métricas mudam conforme se adicionam instâncias. Os arquivos `cargas_N1.json`, `cargas_N2.json` e `cargas_N3.json` são preservados para a análise complementar dos limites calibrados individualmente.

### 6.2 Comando para a bateria

Na raiz do projeto, o comando é:

```powershell
.\rodar_testes.ps1 -Ns 1,2,3
```

O script executa 3 números de instâncias × 3 cenários × 3 níveis de carga = **27 execuções**. Cada execução de Locust dura 60 segundos, seguida de uma pausa padrão de 15 segundos. O script inicia o cluster para cada N, roda os nove testes correspondentes, registra as métricas e derruba os contêineres ao terminar. Reserve cerca de 35 a 50 minutos, podendo variar conforme inicialização, consumo de recursos e falhas.

Para cada execução, o script chama o Locust em modo sem interface (`--headless`), define o ID do post por `POST_ID`, define o host como `http://nginx` e grava os arquivos CSV da execução. A taxa de criação de usuários é calculada para subir os usuários aproximadamente em cinco segundos (`ceil(usuarios/5)`).

### 6.3 Métricas coletadas

O arquivo `locust/resultados/<PC>/resumo.csv` tem uma linha para cada combinação de N, cenário e nível de carga, com as colunas:

- `maquina`: nome do computador.
- `n`: número de instâncias WordPress.
- `cenario`: ID do cenário (1, 2 ou 3).
- `carga`: `min`, `med` ou `max`.
- `usuarios`: usuários virtuais configurados no Locust.
- `requests`: número de requisições HTTP concluídas/contabilizadas.
- `falhas`: requisições que falharam.
- `erro_pct`: percentual de erro calculado a partir das requisições e falhas.
- `media_ms`: tempo médio de resposta.
- `mediana_ms`: mediana do tempo de resposta.
- `p95_ms`: percentil 95 do tempo de resposta.
- `rps`: requisições HTTP por segundo.
- `valido`: `sim` ou `nao`, calculado conforme os critérios de erro do trabalho.

O RPS é a taxa de requisições HTTP — páginas e imagens — e não necessariamente a quantidade de visitantes/tarefas completas por segundo.

### 6.4 Critérios de validade

A exigência do professor é:

- **Carga mínima:** 0% de erros.
- **Carga média:** 0% de erros.
- **Carga máxima:** até 10% de erros.

O script registra `valido=sim` quando a execução cumpre a regra associada ao nível. A calibração foi feita com execuções de 30 segundos e a bateria com execuções de 60 segundos, por isso as taxas precisam ser confirmadas novamente na bateria principal. Uma carga aprovada na calibração não garante, por si só, aprovação na execução de 60 segundos.

### 6.5 Conferir os resultados após a bateria

```powershell
$pasta = ".\locust\resultados\$env:COMPUTERNAME"
$dados = Import-Csv "$pasta\resumo.csv" -Delimiter ","

# Quantidade de execuções registradas (esperado: 27 para uma bateria completa)
$dados.Count

# Resumo por N, cenário, carga, usuários, erros e validade
$dados | Select-Object maquina,n,cenario,carga,usuarios,requests,falhas,erro_pct,media_ms,p95_ms,rps,valido |
    Format-Table -AutoSize

# Mostrar execuções que não atenderam aos critérios
$dados | Where-Object { $_.valido -ne "sim" } |
    Select-Object n,cenario,carga,usuarios,erro_pct,valido |
    Format-Table -AutoSize
```

Se houver menos de 27 linhas, a execução pode ter sido interrompida ou retomada parcialmente. Se `valido=nao` aparecer, não esconda nem exclua a linha: registre o resultado e avalie a necessidade de recalibrar ou reduzir as cargas. Para alterar as cargas e iniciar uma nova rodada, arquive o resumo antigo primeiro. O script de retomada pula combinações já presentes no `resumo.csv`; reaproveitar esse arquivo com cargas alteradas pode misturar medições incompatíveis.

Para preservar a bateria concluída antes de uma nova tentativa:

```powershell
Copy-Item "$pasta\resumo.csv" "$pasta\resumo_bateria_original.csv"
```

Não sobrescreva nem descarte o CSV original sem manter uma cópia.

## 7. Executar o Locust manualmente para diagnóstico

Se precisar validar um cenário sem rodar a bateria completa, com o cluster já iniciado e acessível, execute por exemplo:

```powershell
$env:N = "1"
docker compose run --rm --no-deps `
  -e "POST_ID=5" `
  locust `
  -f /locust/locustfile.py `
  --host http://nginx `
  --headless `
  -u 1 -r 1 -t 10s `
  --only-summary
```

Troque `POST_ID=5` por `8` ou `10` para os outros cenários. Esse teste curto serve para diagnosticar conectividade; não substitui uma execução oficial de 60 segundos.

## 8. Diagnóstico de problemas comuns

### Nginx encerra com `host not found in upstream "wordpress1"`

O Nginx não conseguiu resolver o serviço WordPress quando iniciou. Verifique `docker compose ps -a` e `docker compose logs --tail 80 wordpress1 nginx`. Utilize a versão de `lib.ps1` que inicia o MySQL, aguarda sua prontidão, inicia cada WordPress sequencialmente e só então inicia o Nginx.

### WordPress está `Up`, mas a espera de prontidão expira

Confira se `wp-config.php` existe e examine `docker compose logs --tail 80 wordpress1`. Um Apache iniciado não garante que a verificação de prontidão do script tenha passado. Não comece a calibração enquanto o cluster não completar a validação HTTP.

### Locust tenta conectar em `localhost:80` dentro do contêiner

O WordPress pode responder com um redirecionamento absoluto para `localhost`. O `locustfile.py` usado deve conter a lógica corrigida que transforma o destino do redirecionamento em um caminho relativo e segue a requisição pelo host `http://nginx`, mantendo o cabeçalho `Host: localhost`.

### Porta 80 ocupada ou site não responde

Verifique se outro serviço do Windows está usando a porta 80. Consulte `docker compose ps -a`, `docker compose logs --tail 80 nginx` e, se necessário, `docker compose logs --tail 80 mysql wordpress1 wordpress2 wordpress3`.

### Docker Desktop ou máquina chega ao limite

Feche aplicações desnecessárias, não execute calibração e bateria ao mesmo tempo e acompanhe CPU/RAM do host. Como o Locust roda na mesma máquina, parte dos recursos é consumida pelo gerador de carga. Essa interferência faz parte da arquitetura exigida, mas deve ser considerada na análise.

## 9. Gráficos e comparação entre máquinas

Depois de validar os CSVs, o `graficos.py` deve ser executado a partir da raiz do projeto:

```powershell
python graficos.py
```

O script preparado gera gráficos de barras de tempo médio, P95, RPS e taxa de erro, com N no eixo X e uma barra por carga, separados por cenário. Os gráficos são salvos em `graficos/<NOME-DA-MAQUINA>/`.

Para incluir a máquina do colega, copie a pasta de resultados dessa máquina para `locust/resultados/<NOME-DA-MAQUINA-DO-COLEGA>/`, preservando seus arquivos de calibração e `resumo.csv`, e execute o gerador de gráficos novamente. Não misture arquivos de calibração nem resumos de rodadas diferentes.

**Comparação entre máquinas:** se cada computador usar cargas calibradas diferentes, os resultados descrevem a capacidade de cada ambiente com suas próprias cargas, mas não constituem comparação direta sob a mesma carga. Para comparar latências/RPS entre máquinas de forma controlada, defina cargas comuns que atendam às regras do professor nas duas máquinas e identifique explicitamente no relatório quais cargas foram usadas.

## 10. Estrutura esperada dos resultados

```text
locust/
├─ locustfile.py
└─ resultados/
   └─ <NOME-DA-MAQUINA>/
      ├─ cargas.json                 # último arquivo escrito pela calibração
      ├─ cargas_N1.json              # cópia preservada da calibração N=1
      ├─ cargas_N2.json              # cópia preservada da calibração N=2
      ├─ cargas_N3.json              # cópia preservada da calibração N=3
      ├─ resumo.csv                  # bateria comparativa (até 27 linhas de dados)
      ├─ resumo_bateria_original.csv # opcional: cópia de segurança antes de nova rodada
      └─ calibracao/                 # CSVs detalhados das calibrações
```

## 11. Recomendações para o relatório

Documente a configuração do computador (CPU, memória, sistema operacional), as versões de imagem Docker e Locust, a duração dos testes, os valores de carga e os eventuais testes inválidos. Apresente os gráficos somente após verificar `valido` e explique que o Locust e WordPress compartilham o mesmo host. Compare tempo médio e P95 (experiência percebida), RPS (vazão) e erro (estabilidade). Não conclua que o aumento de instâncias sempre melhora o desempenho: a base de dados é compartilhada e o host tem recursos limitados.
