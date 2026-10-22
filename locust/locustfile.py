import os
import re
from urllib.parse import urlparse

from locust import HttpUser, task, between

# Post alvo do cenario (5 = imagem 1MB, 8 = texto 400KB, 10 = imagem 300KB)
POST_ID = os.environ.get("POST_ID", "5")

# Imagens dentro de /wp-content/uploads referenciadas no HTML do post
IMG_RE = re.compile(r'(?:src|srcset)="([^" ]*?/wp-content/uploads/[^"\s,]+)', re.I)
REDIRECT_CODES = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 5


def caminho_relativo(location):
    """Converte um Location absoluto (ex.: http://localhost/post/) em caminho local."""
    parsed = urlparse(location)
    if parsed.scheme or parsed.netloc:
        caminho = parsed.path or "/"
        if parsed.query:
            caminho += "?" + parsed.query
        return caminho

    # Location relativo, absoluto no caminho ou contendo query string.
    if location.startswith("/"):
        return location
    return "/" + location


class Visitante(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        # O WordPress usa localhost como endereco canonico. Mantemos o Host,
        # mas tratamos os redirecionamentos para que continuem passando pelo nginx.
        self.client.headers["Host"] = "localhost"

    def get_sem_sair_do_nginx(self, url, name):
        """Segue redirecionamentos usando apenas o caminho, nunca localhost como host."""
        resposta = None
        for _ in range(MAX_REDIRECTS + 1):
            resposta = self.client.get(url, name=name, allow_redirects=False)
            if resposta.status_code not in REDIRECT_CODES:
                return resposta

            destino = resposta.headers.get("Location")
            if not destino:
                return resposta

            url = caminho_relativo(destino)

        # Se houver um ciclo ou redirecionamentos demais, devolve a última resposta
        # para que a falha fique visível nas estatísticas do Locust.
        return resposta

    @task
    def ler_post(self):
        resposta = self.get_sem_sair_do_nginx(
            f"/?p={POST_ID}", name=f"post {POST_ID} (pagina)"
        )
        if resposta.status_code != 200:
            return

        # Um navegador real baixaria as imagens do post; simulamos esse comportamento.
        vistos = set()
        for url in IMG_RE.findall(resposta.text):
            caminho = urlparse(url).path
            if not caminho or caminho in vistos:
                continue

            vistos.add(caminho)
            if len(vistos) > 3:
                break

            self.get_sem_sair_do_nginx(
                caminho, name=f"post {POST_ID} (imagem)"
            )