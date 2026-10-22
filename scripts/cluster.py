#!/usr/bin/env python3
"""Mesmo roteiro de lib.ps1, achar_limite.ps1 e rodar_testes.ps1, para este Mac.

Uso:
  python3 scripts/cluster.py preparar
  python3 scripts/cluster.py calibrar --n 1
  python3 scripts/cluster.py bateria --ns 1,2,3
"""

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTEUDO = os.path.join(ROOT, "conteudo")
RESULTADOS = os.path.join(ROOT, "locust", "resultados")
MAQUINA = "MacBookAirs-MacBook-Air"
CENARIOS = [
    {"id": 1, "nome": "imagem_1mb", "post": 5},
    {"id": 2, "nome": "texto_400kb", "post": 8},
    {"id": 3, "nome": "imagem_300kb", "post": 10},
]
DEGRAUS = [5, 10, 20, 40, 80, 120, 160, 240, 320, 480, 640, 960, 1280]
PHP_PROBE = (
    "if (!is_file('/var/www/html/wp-config.php')) { exit(1); } "
    "$s = @fsockopen('127.0.0.1', 80); "
    "if ($s) { fclose($s); exit(0); } exit(1);"
)


def log(msg):
    print(msg, flush=True)


def compose(args, check=True, timeout=None):
    env = os.environ.copy()
    env["N"] = env.get("N", "1")
    proc = subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
    )
    if check and proc.returncode != 0:
        log(proc.stdout or "")
        raise SystemExit(f"docker compose {' '.join(args)} falhou ({proc.returncode})")
    return proc


def service_state(service):
    proc = compose(["ps", "-a", "-q", service], check=False)
    cid = (proc.stdout or "").strip().splitlines()
    if not cid or not cid[0].strip():
        return "missing"
    ins = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", cid[0].strip()],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if ins.returncode != 0:
        return "unknown"
    return ins.stdout.strip()


def wait_mysql(timeout_s=180):
    log("Aguardando o MySQL ficar pronto...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        proc = compose(
            ["exec", "-T", "mysql", "mysqladmin", "ping", "-h", "127.0.0.1", "-uroot", "--password=r00t", "--silent"],
            check=False,
        )
        if proc.returncode == 0:
            log("MySQL pronto.")
            return
        estado = service_state("mysql")
        if estado in ("exited", "dead"):
            log(compose(["logs", "--tail", "80", "mysql"], check=False).stdout or "")
            raise SystemExit("O container mysql encerrou antes de ficar pronto.")
        time.sleep(3)
    log(compose(["logs", "--tail", "80", "mysql"], check=False).stdout or "")
    raise SystemExit("Timeout aguardando o MySQL.")


def wait_wordpress(service, timeout_s=240):
    log(f"Aguardando {service} concluir a inicializacao...")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        estado = service_state(service)
        if estado in ("exited", "dead"):
            log(compose(["logs", "--tail", "80", service], check=False).stdout or "")
            raise SystemExit(f"O container {service} encerrou durante a inicializacao.")
        if estado == "running":
            proc = compose(["exec", "-T", service, "php", "-r", PHP_PROBE], check=False)
            if proc.returncode == 0:
                time.sleep(2)
                log(f"{service} pronto.")
                return
        time.sleep(3)
    log(compose(["ps", "-a"], check=False).stdout or "")
    log(compose(["logs", "--tail", "80", service], check=False).stdout or "")
    raise SystemExit(f"Timeout aguardando {service}.")


def fix_wp_config():
    php = (
        "$p='/var/www/html/wp-config.php';"
        "if (!is_file($p)) { exit(0); }"
        "$t=file_get_contents($p);"
        "if (strpos($t, 'WP_HOME') !== false) { exit(0); }"
        "$e=\"define('WP_HOME', 'http://localhost');\\ndefine('WP_SITEURL', 'http://localhost');\\n\";"
        "$m=\"/* That's all, stop editing!\";"
        "if (strpos($t, $m) !== false) { $t=str_replace($m, $e.$m, $t); }"
        "else { $t.=\"\\n\".$e; }"
        "file_put_contents($p, $t);"
    )
    proc = compose(["exec", "-T", "wordpress1", "php", "-r", php], check=False)
    if proc.returncode != 0:
        log(proc.stdout or "")
        raise SystemExit("Nao foi possivel ajustar o wp-config.php.")
    log("wp-config.php apontando para http://localhost.")


def http_ok(url, timeout=20):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            corpo = resp.read(200000).decode("utf-8", errors="replace")
            return resp.status, corpo
    except Exception as exc:
        return 0, str(exc)


def start_cluster(n, exigir_posts=True):
    if n < 1 or n > 5:
        raise SystemExit(f"N deve estar entre 1 e 5 (recebido: {n}).")
    os.environ["N"] = str(n)
    log(f"\n== Subindo cluster com N={n} ==")
    compose(["down"], check=False, timeout=120)
    log("Subindo MySQL...")
    compose(["up", "-d", "mysql"], timeout=180)
    wait_mysql()
    for i in range(1, n + 1):
        servico = f"wordpress{i}"
        log(f"Subindo {servico}...")
        compose(["up", "-d", servico], timeout=180)
        wait_wordpress(servico)
        if i == 1:
            fix_wp_config()
    log("Subindo Nginx...")
    compose(["up", "-d", "nginx"], timeout=120)
    if not exigir_posts:
        ok = False
        for _ in range(40):
            status, _corpo = http_ok("http://localhost/")
            if status == 200:
                ok = True
                break
            time.sleep(3)
        if not ok:
            log(compose(["logs", "--tail", "80", "nginx"], check=False).stdout or "")
            raise SystemExit("O Nginx nao respondeu em http://localhost/")
        log("Cluster no ar, ainda sem conferir os posts.")
        return
    ok = False
    for _ in range(40):
        status, corpo = http_ok("http://localhost/?p=5")
        if status == 200 and "wp-content/uploads" in corpo:
            ok = True
            break
        time.sleep(3)
    if not ok:
        log(compose(["ps", "-a"], check=False).stdout or "")
        log(compose(["logs", "--tail", "80", "nginx"], check=False).stdout or "")
        raise SystemExit("O site nao respondeu em http://localhost/?p=5")
    for cenario in CENARIOS:
        for _ in range(3):
            http_ok(f"http://localhost/?p={cenario['post']}", timeout=60)
    log("Cluster pronto.")


def preparar():
    os.environ["N"] = "1"
    for nome in ("imagem-1mb.jpg", "imagem-300kb.jpg", "texto-400kb.txt"):
        if not os.path.isfile(os.path.join(CONTEUDO, nome)):
            raise SystemExit(f"Arquivo ausente em conteudo/: {nome}")
    start_cluster(1, exigir_posts=False)
    compose(["cp", os.path.join(ROOT, "scripts", "publicar_posts.php"), "wordpress1:/tmp/publicar_posts.php"])
    compose(["cp", CONTEUDO, "wordpress1:/tmp/conteudo"])
    proc = compose(
        ["exec", "-T", "wordpress1", "php", "/tmp/publicar_posts.php", "/tmp/conteudo"],
        check=False,
        timeout=180,
    )
    log(proc.stdout or "")
    if proc.returncode != 0:
        raise SystemExit("Falha ao publicar os posts.")
    for post, trecho in ((5, "wp-content/uploads"), (8, "Blog post com texto"), (10, "wp-content/uploads")):
        status, corpo = http_ok(f"http://localhost/?p={post}", timeout=60)
        if status != 200 or trecho not in corpo:
            raise SystemExit(f"Post {post} nao ficou publico (HTTP {status}).")
        log(f"Post {post} respondeu HTTP {status}.")
    log("Posts 5, 8 e 10 publicados.")


def read_stats(csv_path):
    if not os.path.isfile(csv_path):
        raise SystemExit(f"CSV do Locust nao foi gerado: {csv_path}")
    with open(csv_path, newline="", encoding="utf-8") as f:
        linhas = list(csv.DictReader(f))
    agg = next((l for l in linhas if l.get("Name") == "Aggregated"), None)
    if not agg:
        raise SystemExit(f"Linha Aggregated nao encontrada em {csv_path}")
    req = float(agg["Request Count"])
    fal = float(agg["Failure Count"])
    erro = 100.0 * fal / req if req else 100.0
    p95 = agg.get("95%") or agg.get("95%ile") or "0"
    return {
        "requests": req,
        "falhas": fal,
        "erro_pct": erro,
        "media_ms": float(agg["Average Response Time"]),
        "mediana_ms": float(agg["Median Response Time"]),
        "p95_ms": float(p95),
        "rps": float(agg["Requests/s"]),
    }


def invoke_teste(post, usuarios, duracao, prefixo):
    destino = os.path.join(RESULTADOS, prefixo)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    spawn = max(1, math.ceil(usuarios / 5))
    csv_locust = "/locust/resultados/" + prefixo.replace("\\", "/")
    compose(
        [
            "--profile", "locust",
            "run", "--rm", "-T", "--no-deps",
            "-e", f"POST_ID={post}",
            "locust",
            "-f", "/locust/locustfile.py",
            "--host", "http://nginx",
            "--headless",
            "-u", str(usuarios),
            "-r", str(spawn),
            "-t", f"{duracao}s",
            "--csv", csv_locust,
            "--only-summary",
        ],
        check=False,
        timeout=duracao + 180,
    )
    return read_stats(destino + "_stats.csv")


def garantir_zero(cenario, usuarios, nome, n, duracao):
    for _ in range(5):
        stats = invoke_teste(
            cenario["post"],
            usuarios,
            duracao,
            f"{MAQUINA}/calibracao/N{n}_c{cenario['id']}_{nome}_u{usuarios}",
        )
        log(f"  {nome}: {usuarios} usuarios -> erro {stats['erro_pct']:.2f}%")
        if stats["erro_pct"] == 0:
            return usuarios
        usuarios = max(1, math.floor(usuarios * 0.75))
        time.sleep(5)
    log(f"Aviso: nao chegou a 0% de erro na carga {nome} do cenario {cenario['id']}.")
    return usuarios


def calibrar(n, duracao):
    start_cluster(n)
    saida = []
    for cenario in CENARIOS:
        log(f"\n=== Cenario {cenario['id']}: {cenario['nome']} (post {cenario['post']}) ===")
        bom = 0
        ruim = 0
        for usuarios in DEGRAUS:
            stats = invoke_teste(
                cenario["post"],
                usuarios,
                duracao,
                f"{MAQUINA}/calibracao/N{n}_c{cenario['id']}_u{usuarios}",
            )
            log(
                f"  {usuarios:5d} usuarios -> erro {stats['erro_pct']:.2f}% | "
                f"media {stats['media_ms']:.0f} ms | {stats['rps']:.1f} req/s"
            )
            if stats["erro_pct"] <= 10:
                bom = usuarios
            else:
                ruim = usuarios
                break
            time.sleep(5)
        if bom == 0:
            raise SystemExit(f"Ja com {DEGRAUS[0]} usuarios o erro passou de 10% no cenario {cenario['id']}.")
        if ruim == 0:
            log(f"Aviso: o limite nao foi atingido ate {bom} usuarios.")
        if ruim > 0:
            meio = int(round((bom + ruim) / 2))
            if bom < meio < ruim:
                stats = invoke_teste(
                    cenario["post"],
                    meio,
                    duracao,
                    f"{MAQUINA}/calibracao/N{n}_c{cenario['id']}_u{meio}",
                )
                log(f"  {meio:5d} usuarios -> erro {stats['erro_pct']:.2f}% (refinamento)")
                if stats["erro_pct"] <= 10:
                    bom = meio
        maximo = bom
        log(f"  Carga maxima: {maximo} usuarios")
        minimo = garantir_zero(cenario, max(1, int(round(maximo * 0.2))), "min", n, duracao)
        media = garantir_zero(cenario, max(minimo + 1, int(round(maximo * 0.5))), "med", n, duracao)
        saida.append({
            "id": cenario["id"],
            "nome": cenario["nome"],
            "post": cenario["post"],
            "min": minimo,
            "med": media,
            "max": maximo,
        })
    pasta = os.path.join(RESULTADOS, MAQUINA)
    os.makedirs(pasta, exist_ok=True)
    payload = {"maquina": MAQUINA, "n_calibracao": n, "cenarios": saida}
    caminho = os.path.join(pasta, "cargas.json")
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    shutil.copyfile(caminho, os.path.join(pasta, f"cargas_N{n}.json"))
    log(f"\nCargas salvas em {caminho}")
    compose(["down"], check=False, timeout=120)


def bateria(ns, duracao, pausa):
    pasta = os.path.join(RESULTADOS, MAQUINA)
    cargas_path = os.path.join(pasta, "cargas.json")
    if not os.path.isfile(cargas_path):
        raise SystemExit("Rode a calibracao antes da bateria.")
    with open(cargas_path, encoding="utf-8") as f:
        cargas = json.load(f)
    resumo = os.path.join(pasta, "resumo.csv")
    if not os.path.isfile(resumo):
        with open(resumo, "w", encoding="ascii", newline="") as f:
            f.write("maquina,n,cenario,carga,usuarios,requests,falhas,erro_pct,media_ms,mediana_ms,p95_ms,rps,valido\n")
    feitos = set()
    with open(resumo, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            feitos.add(f"{linha['n']}|{linha['cenario']}|{linha['carga']}")
    niveis = ("min", "med", "max")
    for n in ns:
        pendente = any(
            f"{n}|{c['id']}|{nivel}" not in feitos
            for c in cargas["cenarios"]
            for nivel in niveis
        )
        if not pendente:
            log(f"N={n} ja concluido, pulando.")
            continue
        start_cluster(n)
        for cenario in cargas["cenarios"]:
            for nivel in niveis:
                chave = f"{n}|{cenario['id']}|{nivel}"
                if chave in feitos:
                    continue
                usuarios = int(cenario[nivel])
                log(f"\n--- N={n} | cenario {cenario['id']} ({cenario['nome']}) | carga {nivel} = {usuarios} usuarios ---")
                stats = invoke_teste(
                    cenario["post"],
                    usuarios,
                    duracao,
                    f"{MAQUINA}/N{n}_c{cenario['id']}_{nivel}",
                )
                valido = stats["erro_pct"] <= 10 if nivel == "max" else stats["erro_pct"] == 0
                log(
                    f"  erro {stats['erro_pct']:.2f}% | media {stats['media_ms']:.0f} ms | "
                    f"p95 {stats['p95_ms']:.0f} ms | {stats['rps']:.1f} req/s | valido={'sim' if valido else 'nao'}"
                )
                with open(resumo, "a", encoding="ascii", newline="") as f:
                    f.write(",".join([
                        MAQUINA,
                        str(n),
                        str(cenario["id"]),
                        nivel,
                        str(usuarios),
                        f"{stats['requests']:.0f}",
                        f"{stats['falhas']:.0f}",
                        f"{stats['erro_pct']:.2f}",
                        f"{stats['media_ms']:.1f}",
                        f"{stats['mediana_ms']:.1f}",
                        f"{stats['p95_ms']:.1f}",
                        f"{stats['rps']:.2f}",
                        "sim" if valido else "nao",
                    ]) + "\n")
                feitos.add(chave)
                time.sleep(pausa)
    compose(["down"], check=False, timeout=120)
    log(f"\nConcluido. Resumo: {resumo}")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("preparar")
    cal = sub.add_parser("calibrar")
    cal.add_argument("--n", type=int, default=1)
    cal.add_argument("--duracao", type=int, default=30)
    bat = sub.add_parser("bateria")
    bat.add_argument("--ns", default="1,2,3")
    bat.add_argument("--duracao", type=int, default=60)
    bat.add_argument("--pausa", type=int, default=15)
    args = parser.parse_args()
    os.chdir(ROOT)
    if args.cmd == "preparar":
        preparar()
    elif args.cmd == "calibrar":
        calibrar(args.n, args.duracao)
    elif args.cmd == "bateria":
        bateria([int(x) for x in args.ns.split(",") if x], args.duracao, args.pausa)


if __name__ == "__main__":
    main()
