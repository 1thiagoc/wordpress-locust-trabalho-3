Estou fazendo um trabalho de Computação Distribuída: testes de carga com Locust em um cluster WordPress. Anexei o PDF do enunciado e os arquivos do projeto. Continue a partir de onde paramos. Não faça nada sem me perguntar antes.

## Enunciado e exigências do professor
- Testar 3 cenários: post com imagem de ~1 MB, post com texto de ~400 KB e post com imagem de ~300 KB.
- Variar a quantidade de instâncias do WordPress (escolhi testar N = 1, 2, 3, 4 e 5).
- Não usar cargas 10/100/1000. São 3 cargas (mínima, média e máxima) descobertas na máquina, sem estourar o limite da aplicação. A máxima pode ter no máximo 10% de erro. A mínima e a média precisam de 0% de erro.
- Rodar em pelo menos 2 máquinas, de preferência uma fraca e uma boa, para ver a diferença de calibragem.
- O Locust deve ficar no mesmo docker-compose, na mesma máquina da aplicação, para vermos a influência do gerador de carga no desempenho (o ideal seria um dispositivo separado, mas o professor quer assim).
- Entrega: gráficos de barras com o número de instâncias no eixo X e as métricas (tempo de resposta, requisições por segundo etc.) no eixo Y, uma barra por carga, mais um relatório em PDF.

## Ambiente
- Minha máquina: i3-7020U, 8 GB de RAM, Windows 10. Meu colega roda na outra máquina.
- Projeto em C:\Users\Jean\wordpress-cluster, com docker-compose (mysql:5.7, wordpress:5.4.2-php7.2-apache x5, nginx:1.19.0) e nginx/nginx-N.conf (N=1..5). O nginx escolhe o config pela variável de ambiente N.
- Imagem do Locust: grubykarol/locust (Locust 1.2.3, baixada).
- Posts dos cenários (públicos, conferidos em aba anônima): ID 5 (imagem 1 MB), ID 8 (texto 400 KB), ID 10 (imagem 300 KB).
- Para subir N instâncias: `$env:N=N; docker compose up -d mysql wordpress1..wordpressN nginx`. Sobem só as instâncias usadas, para não gastar RAM à toa. O `down` não usa -v, para preservar o banco.

## O que já foi feito (arquivos criados)
1. **docker-compose.yml**: o original mais o serviço `locust` (profile "locust", `entrypoint: ["locust"]`, volume ./locust:/locust, ATTACKED_HOST=http://nginx). Ele só roda via `docker compose run`.
2. **locust/locustfile.py**: usuário com wait_time entre 1 e 2 s. Faz GET em `/?p=POST_ID` (variável de ambiente) e baixa até 3 imagens de /wp-content/uploads da página. Usa o header `Host: localhost`, para o WordPress não redirecionar para localhost dentro do container.
3. **lib.ps1**: funções Start-Cluster (down, up com N, espera o site responder e aquece), Invoke-Teste (docker compose run --headless com --csv) e Read-Stats (lê a linha Aggregated do CSV; usa `Import-Csv -Delimiter ","` por causa do pt-BR).
4. **achar_limite.ps1**: com N=1 (a configuração mais fraca), sobe a carga em degraus (5, 10, 20, 40...) de 30 s até o erro passar de 10%, refina pelo ponto médio e define a máxima. Define a mínima (~20% da máxima) e a média (~50%) e reduz 25% até dar 0% de erro. Salva locust\resultados\<PC>\cargas.json.
5. **rodar_testes.ps1**: roda as 45 execuções (5 N x 3 cenários x 3 cargas, 60 s cada, pausa de 15 s). Grava locust\resultados\<PC>\resumo.csv (colunas: maquina, n, cenario, carga, usuarios, requests, falhas, erro_pct, media_ms, mediana_ms, p95_ms, rps, valido). Pode ser retomado: pula o que já está no resumo.
6. **graficos.py**: lê os resumo.csv de todas as máquinas e gera PNGs de barras em graficos\<PC>\ (tempo médio, p95, rps e erro por cenário; X = instâncias, uma barra por carga). Testado com dados falsos e funcionou.

Os scripts .ps1 e o Locust ainda NÃO foram executados de verdade, só revisados. Só o graficos.py foi testado, com dados falsos.

## Próximos passos
1. Rodar `.\achar_limite.ps1` na minha máquina e corrigir qualquer erro (vou colar a saída aqui).
2. Conferir se as cargas calibradas fazem sentido e se N=5 não gera erro nas cargas mínima e média no meu i3 (se gerar, recalibrar com `-N 5`).
3. Rodar `.\rodar_testes.ps1` (cerca de 1 hora). Meu colega faz o mesmo na máquina dele com o mesmo procedimento.
4. Juntar as pastas locust\resultados\<PC> das duas máquinas e rodar `python graficos.py`.
5. Escrever o relatório em PDF: metodologia, calibração das cargas por máquina, gráficos, análise (ganho com mais instâncias, diferença entre as máquinas, influência do Locust no mesmo host) e conclusão.
6. Possíveis extras: gráfico comparando as máquinas e discussão do limite do hardware (RAM de 8 GB com 5 instâncias).

Comece pedindo a saída do achar_limite.ps1 ou me perguntando em que ponto estou.