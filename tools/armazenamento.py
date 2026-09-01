# -*- coding: utf-8 -*-
"""Onde os dados da equipe ficam guardados.

Duas formas, escolhidas sozinhas conforme o ambiente:

  Local   - grava em site/data/veterinarios.json e site/assets/vets/.
            E o que roda no computador da Mychelle.

  GitHub  - grava direto no repositorio, pela API. E o que roda no Render.
            Precisa disso porque o disco do plano gratuito e efemero: tudo
            que fosse escrito em arquivo sumiria no primeiro reinicio. Como
            o GitHub Pages publica a partir do mesmo branch, salvar no
            painel ja atualiza o site, sem passo extra.

So biblioteca padrao: nada para instalar no servidor.
"""
import base64
import json
import os
import re
import secrets
import shutil
import urllib.error
import urllib.request
from datetime import datetime


class ErroDeArmazenamento(Exception):
    """Erro que pode ser mostrado para quem esta usando o painel."""


# =========================================================== disco local ===
class Local:
    def __init__(self, base):
        self.base = base
        self.dados = os.path.join(base, "site", "data", "veterinarios.json")
        self.fotos = os.path.join(base, "site", "assets", "vets")
        self.backups = os.path.join(base, "tools", "backups")

    def descricao(self):
        return "arquivos deste computador"

    def ler(self):
        with open(self.dados, encoding="utf-8") as f:
            return json.load(f)

    def gravar(self, vets, mensagem):
        os.makedirs(self.backups, exist_ok=True)
        if os.path.exists(self.dados):
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(self.dados,
                        os.path.join(self.backups, "veterinarios-" + carimbo + ".json"))
            antigos = sorted(os.listdir(self.backups))
            for velho in antigos[:-30]:
                os.remove(os.path.join(self.backups, velho))

        tmp = self.dados + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(vets, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, self.dados)

    def gravar_foto(self, bruto, nome):
        os.makedirs(self.fotos, exist_ok=True)
        with open(os.path.join(self.fotos, nome), "wb") as f:
            f.write(bruto)
        return "assets/vets/" + nome


# =============================================================== GitHub ====
class GitHub:
    """Le e grava pela API de conteudo do GitHub.

    Cada gravacao e um commit. O GitHub Pages republica sozinho depois,
    entao o site fica atualizado em cerca de um minuto.
    """

    API = "https://api.github.com"

    def __init__(self, repo, branch, token, caminho_dados, caminho_fotos):
        self.repo = repo                 # "usuario/repositorio"
        self.branch = branch
        self.token = token
        self.caminho_dados = caminho_dados
        self.caminho_fotos = caminho_fotos.rstrip("/")
        self._sha = None                 # sha do arquivo, para o proximo commit

    def descricao(self):
        return "repositorio %s (branch %s)" % (self.repo, self.branch)

    # ---------------------------------------------------------- interno --
    def _pedir(self, metodo, caminho, corpo=None):
        url = self.API + caminho
        dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
        req = urllib.request.Request(url, data=dados, method=metodo)
        req.add_header("Authorization", "Bearer " + self.token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "VetHomeCMS")
        if dados:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                texto = r.read().decode("utf-8")
                return json.loads(texto) if texto else {}
        except urllib.error.HTTPError as e:
            detalhe = ""
            try:
                detalhe = json.loads(e.read().decode("utf-8")).get("message", "")
            except Exception:
                pass
            if e.code == 401:
                raise ErroDeArmazenamento(
                    "O token do GitHub foi recusado. Ele pode ter expirado.")
            if e.code == 403:
                raise ErroDeArmazenamento(
                    "O token nao tem permissao de escrita neste repositorio.")
            if e.code == 404:
                raise ErroDeArmazenamento(
                    "Nao encontrei %s no repositorio %s (branch %s)."
                    % (caminho.split("/contents/")[-1].split("?")[0],
                       self.repo, self.branch))
            if e.code == 409:
                raise ErroDeArmazenamento(
                    "Alguem salvou antes de voce. Recarregue a pagina e tente de novo.")
            raise ErroDeArmazenamento("GitHub respondeu %s: %s" % (e.code, detalhe))
        except urllib.error.URLError as e:
            raise ErroDeArmazenamento("Nao consegui falar com o GitHub: %s" % e.reason)

    def _url_conteudo(self, caminho):
        return "/repos/%s/contents/%s" % (self.repo, caminho.lstrip("/"))

    # ------------------------------------------------------------ leitura --
    def ler(self):
        r = self._pedir("GET", self._url_conteudo(self.caminho_dados)
                        + "?ref=" + self.branch)
        self._sha = r.get("sha")
        bruto = base64.b64decode(r.get("content", ""))
        return json.loads(bruto.decode("utf-8"))

    # ------------------------------------------------------------ escrita --
    def gravar(self, vets, mensagem):
        if self._sha is None:
            self.ler()   # precisa do sha atual para o GitHub aceitar a troca

        conteudo = json.dumps(vets, ensure_ascii=False, indent=2) + "\n"
        r = self._pedir("PUT", self._url_conteudo(self.caminho_dados), {
            "message": mensagem,
            "content": base64.b64encode(conteudo.encode("utf-8")).decode(),
            "sha": self._sha,
            "branch": self.branch,
        })
        self._sha = r.get("content", {}).get("sha")

    def gravar_foto(self, bruto, nome):
        caminho = self.caminho_fotos + "/" + nome
        self._pedir("PUT", self._url_conteudo(caminho), {
            "message": "Foto de " + nome,
            "content": base64.b64encode(bruto).decode(),
            "branch": self.branch,
        })
        # o site referencia a foto por este caminho, relativo a raiz dele
        return self.caminho_fotos + "/" + nome


# ============================================================== escolha ====
def escolher(base):
    """GitHub quando as variaveis de ambiente estao la; disco caso contrario."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()

    if token and repo:
        return GitHub(
            repo=repo,
            branch=os.environ.get("GITHUB_BRANCH", "gh-pages").strip(),
            token=token,
            caminho_dados=os.environ.get("GITHUB_ARQUIVO_DADOS",
                                         "data/veterinarios.json").strip(),
            caminho_fotos=os.environ.get("GITHUB_PASTA_FOTOS",
                                         "assets/vets").strip(),
        )
    return Local(base)
