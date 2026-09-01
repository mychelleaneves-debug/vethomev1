# -*- coding: utf-8 -*-
"""CMS da equipe VetHome - so biblioteca padrao do Python.

Roda em dois lugares, com o mesmo codigo:

  No computador da Mychelle (python tools/cms.py)
      escuta em 127.0.0.1:8791, serve o site inteiro para pre-visualizar e
      grava nos arquivos da pasta site/.

  Num servidor gratuito, tipo o Render (com GITHUB_TOKEN e GITHUB_REPO)
      escuta na porta que o servidor mandar, serve SO o painel e grava
      direto no repositorio pela API do GitHub. O site em si continua no
      GitHub Pages: salvar no painel ja republica.

Seguranca: senha guardada como hash PBKDF2 com 200 mil iteracoes (a senha em
si nunca fica escrita). No modo local o painel so existe nesta maquina.

Uso:
    python tools/cms.py --definir-senha     (primeira vez, so no computador)
    python tools/cms.py                     (do dia a dia)
"""
import base64
import datetime
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import sys
import time
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import armazenamento
import operacao

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(BASE, "site")
ADMIN = os.path.join(BASE, "tools", "admin")
CONFIG = os.path.join(BASE, "tools", "cms-config.json")

MAX_FOTO = 8 * 1024 * 1024
SESSAO_HORAS = 12

# Onde os dados moram. Local no computador; GitHub quando as variaveis de
# ambiente do servidor estao la. Ver tools/armazenamento.py.
ARMAZEM = armazenamento.escolher(BASE)
NA_NUVEM = not isinstance(ARMAZEM, armazenamento.Local)

# Onde a operacao da clinica e guardada. E outro lugar de proposito: agenda
# tem nome de cliente e observacao clinica, e o repositorio do site e publico.
# None = nao configurado; o painel mostra a Operacao desativada, com o motivo.
try:
    ARMAZEM_OP = armazenamento.escolher_privado(BASE)
    ERRO_OP = ""
except armazenamento.ErroDeArmazenamento as _e:
    ARMAZEM_OP = None
    ERRO_OP = str(_e)

# O Render (e qualquer servico parecido) diz em qual porta escutar e exige
# que o processo aceite conexoes de fora do container. A existencia da
# variavel PORT e o sinal de que nao estamos num computador pessoal - sem
# isso o painel escutaria so internamente e a pagina ficaria carregando
# para sempre, sem erro nenhum para explicar.
NUM_SERVIDOR = bool(os.environ.get("PORT"))
PORTA = int(os.environ.get("PORT") or 8791)
ENDERECO = "0.0.0.0" if NUM_SERVIDOR else "127.0.0.1"


def _enderecos_do_site():
    """Onde o painel procura as fotos e para onde aponta o botao 'Ver o site'.

    Local: tudo sai do proprio servidor. Na nuvem o site esta em outro lugar
    (GitHub Pages); sem SITE_URL configurada, as fotos ainda aparecem porque
    o GitHub serve o arquivo bruto do repositorio.
    """
    if not NA_NUVEM:
        return "/", "/"
    url = os.environ.get("SITE_URL", "").strip()
    if url:
        if not url.endswith("/"):
            url += "/"
        return url, url
    bruto = ("https://raw.githubusercontent.com/"
             + os.environ.get("GITHUB_REPO", "").strip() + "/"
             + os.environ.get("GITHUB_BRANCH", "gh-pages").strip() + "/")
    return bruto, ""


BASE_FOTOS, URL_SITE = _enderecos_do_site()

sessoes = {}


# ------------------------------------------------------------------ senha --
def hash_senha(senha, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                             salt.encode("utf-8"), 200000)
    return salt, dk.hex()


def _config_do_ambiente():
    """No servidor a senha chega por variavel de ambiente.

    Ela e transformada em hash uma vez, quando o processo sobe, e so o hash
    fica na memoria - o resto do programa nao ve a senha.
    """
    senha = os.environ.get("CMS_SENHA", "").strip()
    if not senha:
        return None
    salt, h = hash_senha(senha)
    return {"salt": salt, "hash": h}


CONFIG_AMBIENTE = _config_do_ambiente()


def ler_config():
    if CONFIG_AMBIENTE:
        return CONFIG_AMBIENTE
    if not os.path.exists(CONFIG):
        return None
    with open(CONFIG, encoding="utf-8") as f:
        return json.load(f)


def definir_senha():
    import getpass
    print("Defina a senha do painel da equipe VetHome.")
    s1 = getpass.getpass("  senha: ")
    if len(s1) < 8:
        print("  precisa de pelo menos 8 caracteres.")
        return
    s2 = getpass.getpass("  repita: ")
    if s1 != s2:
        print("  as senhas nao batem.")
        return
    salt, h = hash_senha(s1)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump({"salt": salt, "hash": h}, f, indent=2)
    print("  pronto. A senha nao fica salva - so o hash dela.")


def senha_confere(senha):
    cfg = ler_config()
    if not cfg:
        return False
    _, h = hash_senha(senha, cfg["salt"])
    return hmac.compare_digest(h, cfg["hash"])


# ------------------------------------------------------------------ dados --
def slugificar(nome):
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "veterinario"


def ler_vets():
    return ARMAZEM.ler()


def gravar_vets(vets, mensagem="Atualiza a equipe pelo painel"):
    ARMAZEM.gravar(vets, mensagem)


def normalizar(v, existentes, id_atual=None):
    """Poe o registro no formato certo. Nao confia no que veio do navegador."""
    nome = str(v.get("nome", "")).strip()
    if not nome:
        raise ValueError("O nome e obrigatorio.")

    slug = slugificar(str(v.get("slug", "")).strip() or nome)
    ocupados = set()
    for x in existentes:
        if x.get("id") != id_atual:
            ocupados.add(x.get("slug"))
    base = slug
    n = 2
    while slug in ocupados:
        slug = base + "-" + str(n)
        n += 1

    areas = v.get("areas", [])
    if isinstance(areas, str):
        areas = areas.split("\n")
    limpas = []
    for a in areas:
        a = str(a).strip()
        if a:
            limpas.append(a)

    try:
        ordem = int(v.get("ordem") or 0)
    except (TypeError, ValueError):
        ordem = 0

    status = "inativo" if v.get("status") == "inativo" else "ativo"

    return {
        "id": id_atual or v.get("id") or slug,
        "nome": nome,
        "cargo": str(v.get("cargo", "")).strip(),
        "especialidade": str(v.get("especialidade", "")).strip(),
        "crmv": str(v.get("crmv", "")).strip(),
        "cidade": str(v.get("cidade", "")).strip(),
        "foto": str(v.get("foto", "")).strip(),
        "descricao": str(v.get("descricao", "")).strip(),
        "areas": limpas,
        "status": status,
        "ordem": ordem,
        "slug": slug,
    }


def salvar_foto(data_url, slug):
    """Recebe a foto em base64 vinda do painel, confere e manda pro armazem."""
    m = re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", data_url, re.S)
    if not m:
        raise ValueError("Formato de imagem nao aceito. Use JPG, PNG ou WEBP.")
    ext = m.group(1)
    if ext == "jpeg":
        ext = "jpg"
    bruto = base64.b64decode(m.group(2))
    if len(bruto) > MAX_FOTO:
        raise ValueError("Imagem muito grande. O limite e 8 MB.")

    # confere pelos bytes iniciais, nao pelo que o navegador disse que era
    ok = (bruto.startswith(b"\xff\xd8\xff")
          or bruto.startswith(b"\x89PNG\r\n\x1a\n")
          or bruto.startswith(b"RIFF"))
    if not ok:
        raise ValueError("O arquivo nao parece ser uma imagem.")

    nome = slug + "-" + secrets.token_hex(3) + "." + ext
    return ARMAZEM.gravar_foto(bruto, nome)


# --------------------------------------------------------------- servidor --
class Handler(BaseHTTPRequestHandler):
    server_version = "VetHomeCMS/1.0"

    def log_message(self, fmt, *args):
        pass

    def responder(self, codigo, corpo=b"", tipo="text/plain; charset=utf-8",
                  extras=None):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extras or []):
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def redirecionar(self, destino):
        self.send_response(302)
        self.send_header("Location", destino)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def json_ok(self, obj, extras=None):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.responder(200, corpo, "application/json; charset=utf-8", extras)

    def json_erro(self, codigo, msg):
        corpo = json.dumps({"erro": msg}, ensure_ascii=False).encode("utf-8")
        self.responder(codigo, corpo, "application/json; charset=utf-8")

    def corpo_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def autenticado(self):
        bruto = self.headers.get("Cookie")
        if not bruto:
            return False
        c = SimpleCookie(bruto)
        if "vethome_cms" not in c:
            return False
        tok = c["vethome_cms"].value
        sessao = sessoes.get(tok)
        if not sessao or sessao["ate"] < time.time():
            sessoes.pop(tok, None)
            return False
        return True

    def quem(self):
        """Quem esta usando o painel, para a auditoria saber de quem foi a acao."""
        bruto = self.headers.get("Cookie")
        if not bruto:
            return ""
        c = SimpleCookie(bruto)
        if "vethome_cms" not in c:
            return ""
        return (sessoes.get(c["vethome_cms"].value) or {}).get("quem", "")

    def do_GET(self):
        caminho = self.path.split("?")[0]

        # o Render fica cutucando um endereco para saber se o painel esta de pe
        if caminho == "/healthz":
            return self.responder(200, b"ok")

        if caminho == "/api/sessao":
            return self.json_ok({"autenticado": self.autenticado(),
                                 "configurado": ler_config() is not None,
                                 "baseFotos": BASE_FOTOS,
                                 "urlSite": URL_SITE,
                                 "quem": self.quem(),
                                 "operacao": ARMAZEM_OP is not None,
                                 "operacaoMotivo": ERRO_OP or (
                                     "" if ARMAZEM_OP else
                                     "Falta configurar o repositório privado "
                                     "(GITHUB_REPO_DADOS) para a operação da clínica."),
                                 "operacaoOnde": ARMAZEM_OP.descricao() if ARMAZEM_OP else ""})

        if caminho == "/api/vets":
            if not self.autenticado():
                return self.json_erro(401, "Faca login para ver os dados.")
            try:
                return self.json_ok(ler_vets())
            except armazenamento.ErroDeArmazenamento as e:
                return self.json_erro(502, str(e))
            except Exception as e:
                return self.json_erro(500, "Nao consegui ler a equipe: " + str(e))

        if caminho.startswith("/api/op/"):
            if not self.autenticado():
                return self.json_erro(401, "Faca login para ver os dados.")
            try:
                return self.op_get(caminho[len("/api/op/"):])
            except ValueError as e:
                return self.json_erro(400, str(e))
            except armazenamento.ErroDeArmazenamento as e:
                return self.json_erro(502, str(e))
            except Exception as e:
                return self.json_erro(500, "Erro no servidor: " + str(e))

        if caminho in ("/admin", "/admin/"):
            return self.arquivo(os.path.join(ADMIN, "index.html"))

        if caminho.startswith("/admin/"):
            return self.arquivo(os.path.join(ADMIN, caminho[len("/admin/"):]))

        # Na nuvem o site nao mora aqui - ele esta no GitHub Pages. Servir uma
        # copia velha do site so confundiria, entao tudo vai para o painel.
        if NA_NUVEM:
            return self.redirecionar("/admin")

        rel = caminho.lstrip("/") or "index.html"
        return self.arquivo(os.path.join(SITE, rel))

    def do_POST(self):
        caminho = self.path.split("?")[0]
        try:
            if caminho == "/api/login":
                dados = self.corpo_json()
                if not senha_confere(str(dados.get("senha", ""))):
                    time.sleep(1)
                    return self.json_erro(401, "Senha incorreta.")
                tok = secrets.token_urlsafe(32)
                sessoes[tok] = {"ate": time.time() + SESSAO_HORAS * 3600,
                                "quem": str(dados.get("quem", "")).strip()[:60]}
                cookie = ("vethome_cms=" + tok +
                          "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" +
                          str(SESSAO_HORAS * 3600))
                # na nuvem a conexao e https, entao o cookie so trafega nela
                if NA_NUVEM:
                    cookie += "; Secure"
                return self.json_ok({"ok": True}, [("Set-Cookie", cookie)])

            if caminho == "/api/logout":
                bruto = self.headers.get("Cookie")
                if bruto:
                    c = SimpleCookie(bruto)
                    if "vethome_cms" in c:
                        sessoes.pop(c["vethome_cms"].value, None)
                return self.json_ok(
                    {"ok": True},
                    [("Set-Cookie", "vethome_cms=; Path=/; Max-Age=0")])

            if not self.autenticado():
                return self.json_erro(401, "Sessao expirada. Faca login de novo.")

            if caminho == "/api/vets":
                return self.salvar_vet()
            if caminho == "/api/ordem":
                return self.salvar_ordem()
            if caminho.startswith("/api/op/"):
                return self.op_post(caminho[len("/api/op/"):], self.corpo_json())

            return self.json_erro(404, "Rota nao encontrada.")

        except operacao.ConflitoDeAgenda as e:
            # 409 = conflito. O painel usa a lista para dizer o que houve e,
            # quando for encaixe, oferecer o botao de confirmar.
            corpo = json.dumps({"erro": "Conflito de agenda.",
                                "conflitos": e.problemas,
                                "podeEncaixar": True}, ensure_ascii=False)
            return self.responder(409, corpo.encode("utf-8"),
                                  "application/json; charset=utf-8")

        except ValueError as e:
            return self.json_erro(400, str(e))
        except armazenamento.ErroDeArmazenamento as e:
            return self.json_erro(502, str(e))
        except Exception as e:
            return self.json_erro(500, "Erro no servidor: " + str(e))

    def salvar_vet(self):
        dados = self.corpo_json()
        vets = ler_vets()
        id_atual = dados.get("id")

        existe = None
        for v in vets:
            if v.get("id") == id_atual:
                existe = v
                break

        registro = normalizar(dados, vets, id_atual if existe else None)

        foto_nova = dados.get("fotoNova")
        if foto_nova:
            registro["foto"] = salvar_foto(foto_nova, registro["slug"])
        elif existe and not registro["foto"]:
            registro["foto"] = existe.get("foto", "")

        if existe:
            vets[vets.index(existe)] = registro
            mensagem = "Atualiza " + registro["nome"] + " pelo painel"
        else:
            registro["id"] = registro["slug"]
            if not registro["ordem"]:
                maior = 0
                for v in vets:
                    if v.get("ordem", 0) > maior:
                        maior = v.get("ordem", 0)
                registro["ordem"] = maior + 1
            vets.append(registro)
            mensagem = "Adiciona " + registro["nome"] + " pelo painel"

        vets.sort(key=lambda v: v.get("ordem", 0))
        gravar_vets(vets, mensagem)
        return self.json_ok({"ok": True, "vet": registro})

    def salvar_ordem(self):
        dados = self.corpo_json()
        ids = dados.get("ids") or []
        vets = ler_vets()
        posicao = {}
        for n, i in enumerate(ids):
            posicao[i] = n + 1
        for v in vets:
            if v.get("id") in posicao:
                v["ordem"] = posicao[v["id"]]
        vets.sort(key=lambda v: v.get("ordem", 0))
        gravar_vets(vets, "Reordena a equipe pelo painel")
        return self.json_ok({"ok": True})

    # ------------------------------------------------------- operacao ----
    def _consulta(self, nome, padrao=""):
        """Um parametro da URL, tipo ?data=2026-09-01."""
        from urllib.parse import parse_qs, urlparse
        valores = parse_qs(urlparse(self.path).query).get(nome)
        return valores[0] if valores else padrao

    def _vets(self):
        """A equipe, que e a chave de tudo na operacao. Vem do mesmo arquivo
        que alimenta o site - nao existe cadastro paralelo de veterinario."""
        return [v for v in ler_vets() if v.get("status") != "inativo"]

    def op_get(self, rota):
        arm = ARMAZEM_OP
        vets = self._vets()

        if rota == "inicio":
            # tudo que o painel precisa para desenhar as telas, de uma vez so
            return self.json_ok({
                "vets": [{"id": v.get("id"), "nome": v.get("nome"),
                          "especialidade": v.get("especialidade", ""),
                          "foto": v.get("foto", "")} for v in vets],
                "tipos": operacao.TIPOS_ATENDIMENTO,
                "status": operacao.STATUS,
                "statusRotulo": operacao.STATUS_ROTULO,
                "motivosCancelamento": operacao.MOTIVOS_CANCELAMENTO,
                "motivosBloqueio": operacao.MOTIVOS_BLOQUEIO,
                "tiposAusencia": operacao.TIPOS_AUSENCIA,
                "ausenciaRotulo": operacao.AUSENCIA_ROTULO,
                "dias": operacao.DIAS,
                "duracaoPadrao": operacao.DURACAO_PADRAO,
                "hoje": datetime.date.today().isoformat(),
            })

        if rota == "resumo":
            return self.json_ok(operacao.resumo(arm, vets))
        if rota == "atendimentos":
            return self.json_ok(operacao.listar_atendimentos(arm))
        if rota == "pacientes":
            return self.json_ok(operacao.listar_pacientes(arm))
        if rota == "disponibilidade":
            return self.json_ok(operacao.listar_disponibilidade(arm))
        if rota == "bloqueios":
            return self.json_ok(operacao.listar_bloqueios(arm))
        if rota == "ausencias":
            return self.json_ok(operacao.listar_ausencias(arm))
        if rota == "auditoria":
            return self.json_ok(operacao.listar_auditoria(arm))
        if rota == "escala":
            dia = operacao.como_data(self._consulta(
                "data", datetime.date.today().isoformat()))
            return self.json_ok(operacao.escala_do_dia(arm, vets, dia))
        if rota == "escala-semana":
            dia = operacao.como_data(self._consulta(
                "data", datetime.date.today().isoformat()))
            return self.json_ok([operacao.escala_do_dia(arm, vets, d)
                                 for d in operacao.semana_de(dia)])
        if rota == "horarios":
            return self.json_ok(operacao.horarios_livres(
                arm, vets, self._consulta("vet"), self._consulta("data"),
                self._consulta("duracao") or None))

        return self.json_erro(404, "Rota nao encontrada.")

    def op_post(self, rota, dados):
        arm = ARMAZEM_OP
        vets = self._vets()
        eu = self.quem()

        if rota == "atendimento":
            registro, avisos = operacao.salvar_atendimento(arm, vets, dados, eu)
            return self.json_ok({"ok": True, "atendimento": registro,
                                 "avisos": avisos})
        if rota == "atendimento/status":
            return self.json_ok({"ok": True, "atendimento": operacao.mudar_status(
                arm, dados.get("id"), dados.get("status"), eu)})
        if rota == "atendimento/cancelar":
            return self.json_ok({"ok": True, "atendimento": operacao.cancelar_atendimento(
                arm, dados.get("id"), dados.get("motivo"),
                dados.get("observacao"), eu)})
        if rota == "paciente":
            return self.json_ok({"ok": True,
                                 "paciente": operacao.salvar_paciente(arm, dados, eu)})
        if rota == "disponibilidade":
            return self.json_ok({"ok": True, "disponibilidade":
                                 operacao.salvar_disponibilidade(
                                     arm, dados.get("vetId"), dados, eu)})
        if rota == "bloqueio":
            return self.json_ok({"ok": True,
                                 "bloqueio": operacao.salvar_bloqueio(arm, dados, eu)})
        if rota == "bloqueio/remover":
            operacao.remover_bloqueio(arm, dados.get("id"), eu)
            return self.json_ok({"ok": True})
        if rota == "ausencia":
            return self.json_ok({"ok": True,
                                 "ausencia": operacao.salvar_ausencia(arm, dados, eu)})
        if rota == "ausencia/remover":
            operacao.remover_ausencia(arm, dados.get("id"), eu)
            return self.json_ok({"ok": True})
        if rota == "escala":
            return self.json_ok({"ok": True,
                                 "escala": operacao.salvar_escala(arm, dados, eu)})
        if rota == "escala/remover":
            operacao.remover_escala(arm, dados.get("data"), eu)
            return self.json_ok({"ok": True})

        return self.json_erro(404, "Rota nao encontrada.")

    def arquivo(self, caminho):
        caminho = os.path.normpath(caminho)
        if not (caminho.startswith(SITE) or caminho.startswith(ADMIN)):
            return self.responder(403, b"acesso negado")
        if os.path.isdir(caminho):
            caminho = os.path.join(caminho, "index.html")
        if not os.path.isfile(caminho):
            return self.responder(404, b"nao encontrado")
        tipo, _ = mimetypes.guess_type(caminho)
        if not tipo:
            tipo = "application/octet-stream"
        if tipo.startswith("text/") or tipo in ("application/javascript",
                                                "application/json"):
            tipo += "; charset=utf-8"
        with open(caminho, "rb") as f:
            corpo = f.read()
        self.responder(200, corpo, tipo)


def main():
    if "--definir-senha" in sys.argv:
        return definir_senha()

    if ler_config() is None:
        if NA_NUVEM:
            print("Falta a variavel de ambiente CMS_SENHA no servidor.")
        else:
            print("Nenhuma senha definida ainda. Rode primeiro:")
            print("    python tools/cms.py --definir-senha")
        return

    os.makedirs(ADMIN, exist_ok=True)

    # Num servidor, gravar em arquivo perde tudo no proximo reinicio. Melhor
    # gritar no log do que descobrir isso quando os cadastros sumirem.
    if NUM_SERVIDOR and not NA_NUVEM:
        print("=" * 68)
        print("ATENCAO: faltam as variaveis GITHUB_TOKEN e GITHUB_REPO.")
        print("Sem elas o painel grava em arquivo, e o disco deste servidor")
        print("e apagado a cada reinicio: todo cadastro novo seria perdido.")
        print("Adicione as duas em Environment e salve.")
        print("=" * 68)

    srv = ThreadingHTTPServer((ENDERECO, PORTA), Handler)
    print("VetHome CMS no ar")
    print("  dados  " + ARMAZEM.descricao())
    if NA_NUVEM:
        print("  painel /admin na porta " + str(PORTA))
    else:
        print("  site   http://localhost:" + str(PORTA) + "/")
        print("  painel http://localhost:" + str(PORTA) + "/admin")
        print("  (Ctrl+C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
