# -*- coding: utf-8 -*-
"""CMS da equipe VetHome - servidor local, so biblioteca padrao do Python.

O que ele faz:
  - serve o site igual ao serve.ps1 (porta 8791)
  - serve o painel em /admin, protegido por senha
  - le e grava site/data/veterinarios.json
  - recebe as fotos e grava em site/assets/vets/

Seguranca: escuta so em 127.0.0.1, entao o painel nao existe pela rede - e
preciso estar nesta maquina. Alem disso pede senha, guardada como hash
PBKDF2 com 200 mil iteracoes (a senha em si nunca fica escrita).

Uso:
    python tools/cms.py --definir-senha     (primeira vez)
    python tools/cms.py                     (do dia a dia)
"""
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(BASE, "site")
ADMIN = os.path.join(BASE, "tools", "admin")
DADOS = os.path.join(SITE, "data", "veterinarios.json")
FOTOS = os.path.join(SITE, "assets", "vets")
CONFIG = os.path.join(BASE, "tools", "cms-config.json")
BACKUPS = os.path.join(BASE, "tools", "backups")

PORTA = 8791
MAX_FOTO = 8 * 1024 * 1024
SESSAO_HORAS = 12

sessoes = {}


# ------------------------------------------------------------------ senha --
def hash_senha(senha, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"),
                             salt.encode("utf-8"), 200000)
    return salt, dk.hex()


def ler_config():
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
    with open(DADOS, encoding="utf-8") as f:
        return json.load(f)


def gravar_vets(vets):
    """Grava com backup e de forma atomica: se faltar energia no meio da
    escrita, o arquivo original continua inteiro."""
    os.makedirs(BACKUPS, exist_ok=True)
    if os.path.exists(DADOS):
        carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy(DADOS, os.path.join(BACKUPS, "veterinarios-" + carimbo + ".json"))
        antigos = sorted(os.listdir(BACKUPS))
        for velho in antigos[:-30]:
            os.remove(os.path.join(BACKUPS, velho))

    tmp = DADOS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(vets, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, DADOS)


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
    """Recebe a foto em base64 vinda do painel e grava em disco."""
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

    os.makedirs(FOTOS, exist_ok=True)
    nome = slug + "-" + secrets.token_hex(3) + "." + ext
    with open(os.path.join(FOTOS, nome), "wb") as f:
        f.write(bruto)
    return "assets/vets/" + nome


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
        exp = sessoes.get(tok)
        if not exp or exp < time.time():
            sessoes.pop(tok, None)
            return False
        return True

    def do_GET(self):
        caminho = self.path.split("?")[0]

        if caminho == "/api/sessao":
            return self.json_ok({"autenticado": self.autenticado(),
                                 "configurado": ler_config() is not None})

        if caminho == "/api/vets":
            if not self.autenticado():
                return self.json_erro(401, "Faca login para ver os dados.")
            return self.json_ok(ler_vets())

        if caminho in ("/admin", "/admin/"):
            return self.arquivo(os.path.join(ADMIN, "index.html"))

        if caminho.startswith("/admin/"):
            return self.arquivo(os.path.join(ADMIN, caminho[len("/admin/"):]))

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
                sessoes[tok] = time.time() + SESSAO_HORAS * 3600
                cookie = ("vethome_cms=" + tok +
                          "; Path=/; HttpOnly; SameSite=Strict; Max-Age=" +
                          str(SESSAO_HORAS * 3600))
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

            return self.json_erro(404, "Rota nao encontrada.")

        except ValueError as e:
            return self.json_erro(400, str(e))
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
        else:
            registro["id"] = registro["slug"]
            if not registro["ordem"]:
                maior = 0
                for v in vets:
                    if v.get("ordem", 0) > maior:
                        maior = v.get("ordem", 0)
                registro["ordem"] = maior + 1
            vets.append(registro)

        vets.sort(key=lambda v: v.get("ordem", 0))
        gravar_vets(vets)
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
        gravar_vets(vets)
        return self.json_ok({"ok": True})

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
        print("Nenhuma senha definida ainda. Rode primeiro:")
        print("    python tools/cms.py --definir-senha")
        return

    os.makedirs(ADMIN, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORTA), Handler)
    print("VetHome CMS no ar")
    print("  site   http://localhost:" + str(PORTA) + "/")
    print("  painel http://localhost:" + str(PORTA) + "/admin")
    print("  (Ctrl+C para parar)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrado")


if __name__ == "__main__":
    main()
