"""Gera os graficos de barras a partir de locust/resultados/<maquina>/resumo.csv.

Uso:  python graficos.py
Requer: pip install matplotlib

Saida: graficos/<maquina>/<cenario>_<metrica>.png
Eixo X = numero de instancias do WordPress; uma barra por carga (min/med/max).
"""
import csv
import glob
import os
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

RAIZ = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.join(RAIZ, "locust", "resultados")
SAIDA = os.path.join(RAIZ, "graficos")

CENARIOS = {1: "Imagem de ~1 MB", 2: "Texto de ~400 KB", 3: "Imagem de ~300 KB"}
NIVEIS = [("min", "Carga mínima"), ("med", "Carga média"), ("max", "Carga máxima")]
CORES = {"min": "#9fd3a8", "med": "#f2c879", "max": "#e58a8a"}
METRICAS = [
    ("media_ms", "Tempo médio de resposta (ms)", "tempo_medio"),
    ("p95_ms", "Tempo de resposta p95 (ms)", "tempo_p95"),
    ("rps", "Requisições por segundo", "rps"),
    ("erro_pct", "Taxa de erro (%)", "erro"),
]


def ler(caminho):
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def grafico(maquina, cenario, linhas, chave, rotulo_y, arquivo):
    ns = sorted({int(l["n"]) for l in linhas})
    valores = {(int(l["n"]), l["carga"]): float(l[chave]) for l in linhas}
    usuarios = {l["carga"]: int(l["usuarios"]) for l in linhas}
    niveis = [nivel for nivel in NIVEIS if any(carga == nivel[0] for carga in (l["carga"] for l in linhas))]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    largura = 0.26
    x = np.arange(len(ns))
    deslocamentos = np.linspace(-(len(niveis) - 1) / 2, (len(niveis) - 1) / 2, len(niveis))
    for deslocamento, (nivel, nome) in zip(deslocamentos, niveis):
        ys = [valores.get((n, nivel), np.nan) for n in ns]
        barras = ax.bar(x + deslocamento * largura, ys, largura, color=CORES[nivel],
                        edgecolor="black", linewidth=0.6,
                        label=f"{nome} ({usuarios.get(nivel, '?')} usuários)")
        for barra, valor in zip(barras, ys):
            if not np.isfinite(valor):
                continue
            ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height(),
                    f"{valor:.1f}", ha="center", va="bottom", fontsize=7)
    if chave == "erro_pct":
        ax.axhline(10, color="red", linestyle="--", linewidth=1)
        ax.text(len(ns) - 0.5, 10, " limite 10%", color="red", va="bottom", ha="right", fontsize=8)
    ax.set_xticks(x)
    ax.set_xticklabels([str(n) for n in ns])
    ax.set_xlabel("Número de instâncias do WordPress")
    ax.set_ylabel(rotulo_y)
    ax.set_title(f"{CENARIOS.get(cenario, cenario)} — {maquina}")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(arquivo, dpi=150)
    plt.close(fig)


def main():
    arquivos = glob.glob(os.path.join(BASE, "*", "resumo.csv"))
    if not arquivos:
        raise SystemExit(f"Nenhum resumo.csv encontrado em {BASE}")
    total = 0
    for caminho in sorted(arquivos):
        maquina = os.path.basename(os.path.dirname(caminho))
        por_cenario = defaultdict(list)
        for linha in ler(caminho):
            por_cenario[int(linha["cenario"])].append(linha)
        pasta = os.path.join(SAIDA, maquina)
        os.makedirs(pasta, exist_ok=True)
        for cenario, linhas in sorted(por_cenario.items()):
            for chave, rotulo, sufixo in METRICAS:
                arquivo = os.path.join(pasta, f"cenario{cenario}_{sufixo}.png")
                grafico(maquina, cenario, linhas, chave, rotulo, arquivo)
                total += 1
        print(f"{maquina}: gráficos em {pasta}")
    print(f"{total} gráficos gerados.")


if __name__ == "__main__":
    main()
