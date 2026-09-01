# -*- coding: utf-8 -*-
"""Onde os dados ficam guardados.

Dois lugares, com proposito diferente:

  PUBLICO   a equipe que aparece no site (site/data/veterinarios.json e as
            fotos). Vai para o repositorio do site, que e publico - e tem
            que ser, senao o GitHub Pages nao publica.

  PRIVADO   a operacao da clinica: agendamentos, pacientes, tutores,
            disponibilidade, ausencias. Tem nome de cliente e observacao
            clinica, entao NUNCA pode ir para o repositorio publico. Vai
            para um repositorio privado separado.

E duas formas de gravar, escolhidas sozinhas conforme o ambiente:

  Local     arquivos deste computador. E o que roda na maquina da Mychelle.
  GitHub    grava pela API. E o que roda no Render, porque o disco do plano
            gratuito e efemero: tudo que fosse escrito em arquivo sumiria no
            primeiro reinicio.

So biblioteca padrao: nada para instalar no servidor.
"""
import base64
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime


class ErroDeArmazenamento(Exception):
    """Erro que pode ser mostrado para quem esta usando o painel."""


class ArmazemIndisponivel(ErroDeArmazenamento):
    """Nao ha onde guardar os dados da operacao (falta configurar)."""


# =========================================================== disco local ===
class Local:
    """Arquivos numa pasta deste computador."""

    def __init__(self, base, pasta_dados=None, pasta_fotos=None, rotulo=None):
        self.base = base
        self.raiz = pasta_dados or os.path.join(base, "site", "data")
        self.fotos = pasta_fotos or os.path.join(base, "site", "assets", "vets")
        self.backups = os.path.join(base, "tools", "backups")
        self.rotulo = rotulo or "arquivos deste computador"

    def descricao(self):
        return self.rotulo

    # ------------------------------------------------------- um arquivo --
    def _caminho(self, nome):
        return os.path.join(self.raiz, nome.replace("/", os.sep))

    def ler_arquivo(self, nome, padrao=None):
        caminho = self._caminho(nome)
        if not os.path.exists(caminho):
            if padrao is None:
                raise ErroDeArmazenamento("Nao encontrei o arquivo " + nome + ".")
            return padrao
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)

    def gravar_arquivo(self, nome, dados, mensagem):
        caminho = self._caminho(nome)
        pasta = os.path.dirname(caminho)
        if pasta:
            os.makedirs(pasta, exist_ok=True)

        # backup so do arquivo da equipe, que e o unico editado a mao antes
        if nome == "veterinarios.json" and os.path.exists(caminho):
            os.makedirs(self.backups, exist_ok=True)
            carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy(caminho,
                        os.path.join(self.backups, "veterinarios-" + carimbo + ".json"))
            antigos = sorted(os.listdir(self.backups))
            for velho in antigos[:-30]:
                os.remove(os.path.join(self.backups, velho))

        # grava num temporario e troca: se faltar energia no meio da escrita,
        # o arquivo original continua inteiro
        tmp = caminho + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, caminho)

    # --------------------------------------------------- compatibilidade --
    def ler(self):
        return self.ler_arquivo("veterinarios.json")

    def gravar(self, vets, mensagem):
        self.gravar_arquivo("veterinarios.json", vets, mensagem)

    def gravar_foto(self, bruto, nome):
        os.makedirs(self.fotos, exist_ok=True)
        with open(os.path.join(self.fotos, nome), "wb") as f:
            f.write(bruto)
        return "assets/vets/" + nome


# =============================================================== GitHub ====
class GitHub:
    """Le e grava pela API de conteudo do GitHub.

    Cada gravacao e um commit. No repositorio do site, o GitHub Pages
    republica sozinho depois; no repositorio privado da operacao ninguem
    publica nada - ele so serve de cofre.
    """

    API = "https://api.github.com"

    def __init__(self, repo, branch, token, caminho_dados, caminho_fotos):
        self.repo = repo                 # "usuario/repositorio"
        self.branch = branch
        self.token = token
        self.caminho_dados = caminho_dados.rstrip("/")
        self.caminho_fotos = caminho_fotos.rstrip("/")
        self._shas = {}                  # caminho -> sha, para o proximo commit

    def descricao(self):
        return "repositorio %s (branch %s)" % (self.repo, self.branch)

    # ---------------------------------------------------------- interno --
    def _pedir(self, metodo, caminho, corpo=None, aceita_404=False):
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
                    "O token nao tem permissao de escrita em %s." % self.repo)
            if e.code == 404:
                if aceita_404:
                    return None
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

    def _completo(self, nome):
        return (self.caminho_dados + "/" + nome) if self.caminho_dados else nome

    # ------------------------------------------------------- um arquivo --
    def ler_arquivo(self, nome, padrao=None):
        caminho = self._completo(nome)
        r = self._pedir("GET", self._url_conteudo(caminho) + "?ref=" + self.branch,
                        aceita_404=(padrao is not None))
        if r is None:
            # arquivo ainda nao existe no repositorio; sera criado no 1o save
            self._shas.pop(caminho, None)
            return padrao
        self._shas[caminho] = r.get("sha")
        bruto = base64.b64decode(r.get("content", ""))
        return json.loads(bruto.decode("utf-8"))

    def gravar_arquivo(self, nome, dados, mensagem):
        caminho = self._completo(nome)
        if caminho not in self._shas:
            # precisa do sha atual para o GitHub aceitar a troca
            self.ler_arquivo(nome, padrao=[])

        conteudo = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
        corpo = {
            "message": mensagem,
            "content": base64.b64encode(conteudo.encode("utf-8")).decode(),
            "branch": self.branch,
        }
        sha = self._shas.get(caminho)
        if sha:
            corpo["sha"] = sha
        r = self._pedir("PUT", self._url_conteudo(caminho), corpo)
        self._shas[caminho] = r.get("content", {}).get("sha")

    # --------------------------------------------------- compatibilidade --
    def ler(self):
        return self.ler_arquivo("veterinarios.json")

    def gravar(self, vets, mensagem):
        self.gravar_arquivo("veterinarios.json", vets, mensagem)

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
def _pasta_de(caminho):
    """A pasta de "data/veterinarios.json" e "data"; a de um nome solto e "".

    A variavel de ambiente guarda o arquivo inteiro por compatibilidade, mas
    quem grava precisa da pasta, para poder escrever os outros arquivos ao lado.
    """
    caminho = (caminho or "").strip().strip("/")
    return caminho.rsplit("/", 1)[0] if "/" in caminho else ""



def escolher(base):
    """Onde mora a equipe que aparece no site.

    GitHub quando as variaveis de ambiente estao la; disco caso contrario.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "").strip()

    if token and repo:
        return GitHub(
            repo=repo,
            branch=os.environ.get("GITHUB_BRANCH", "gh-pages").strip(),
            token=token,
            caminho_dados=_pasta_de(os.environ.get("GITHUB_ARQUIVO_DADOS",
                                                   "data/veterinarios.json")),
            caminho_fotos=os.environ.get("GITHUB_PASTA_FOTOS",
                                         "assets/vets").strip(),
        )
    return Local(base)


def escolher_privado(base):
    """Onde mora a operacao da clinica (dados de cliente).

    Nunca no repositorio do site. Ou um repositorio privado proprio, ou a
    pasta dados/ deste computador, que fica fora do Git.

    Devolve None quando esta num servidor sem repositorio privado
    configurado - gravar em disco la perderia tudo no proximo reinicio, e
    e melhor o painel dizer isso do que fingir que salvou.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO_DADOS", "").strip()
    publico = os.environ.get("GITHUB_REPO", "").strip()

    if token and repo:
        if publico and repo.lower() == publico.lower():
            raise ErroDeArmazenamento(
                "GITHUB_REPO_DADOS aponta para o repositorio do site, que e "
                "publico. Os agendamentos tem nome de cliente e precisam de um "
                "repositorio privado separado.")
        return GitHub(
            repo=repo,
            branch=os.environ.get("GITHUB_BRANCH_DADOS", "main").strip(),
            token=token,
            caminho_dados=os.environ.get("GITHUB_PASTA_DADOS", "dados").strip(),
            caminho_fotos="",
        )

    if os.environ.get("PORT"):
        return None   # num servidor, sem repositorio privado, nao ha onde guardar

    return Local(base,
                 pasta_dados=os.path.join(base, "dados"),
                 rotulo="pasta dados/ deste computador")
