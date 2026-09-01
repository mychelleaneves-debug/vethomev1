# -*- coding: utf-8 -*-
"""Teste do ciclo completo do CMS, do login ate o veterinario sumir do site.

Roda contra o servidor em 127.0.0.1:8791. Nao mexe nos veterinarios reais:
cria um de teste, exercita tudo com ele e apaga no fim.
"""
import base64
import io
import json
import os
import sys
import urllib.request
import urllib.error
from http.cookiejar import CookieJar

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8791"
SENHA = "senha-de-teste-vethome"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(RAIZ, "site", "data", "veterinarios.json")

cookies = CookieJar()
abridor = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))

falhas = []
passos = 0


def checa(descricao, condicao, detalhe=""):
    global passos
    passos += 1
    if condicao:
        print("  OK   %s" % descricao)
    else:
        print("  FALHA %s   %s" % (descricao, detalhe))
        falhas.append(descricao)


def pedir(metodo, rota, corpo=None):
    dados = json.dumps(corpo).encode("utf-8") if corpo is not None else None
    req = urllib.request.Request(BASE + rota, data=dados, method=metodo)
    if dados:
        req.add_header("Content-Type", "application/json")
    try:
        with abridor.open(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        corpo_erro = e.read().decode("utf-8")
        try:
            return e.code, json.loads(corpo_erro)
        except ValueError:
            return e.code, {"erro": corpo_erro}


def buscar(rota):
    """O que o VISITANTE recebe, sem cookie de admin."""
    req = urllib.request.Request(BASE + rota)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.read().decode("utf-8")


def png_de_teste():
    """PNG 1x1 valido, so para exercitar o upload."""
    bruto = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    return "data:image/png;base64," + base64.b64encode(bruto).decode()


print("=" * 62)
print("TESTE DO CMS DA EQUIPE")
print("=" * 62)

# --------------------------------------------------------------- 0. login --
print("\n[0] Login e seguranca")
cod, _ = pedir("GET", "/api/vets")
checa("sem senha, a API recusa (401)", cod == 401, "veio %s" % cod)

cod, r = pedir("POST", "/api/login", {"senha": "senha-errada"})
checa("senha errada e recusada", cod == 401, "veio %s" % cod)

cod, r = pedir("POST", "/api/login", {"senha": SENHA})
checa("senha certa entra", cod == 200 and r.get("ok"), str(r))

cod, lista = pedir("GET", "/api/vets")
checa("com sessao, a API responde", cod == 200 and isinstance(lista, list))
total_inicial = len(lista)
print("       %d veterinarios cadastrados" % total_inicial)

# ------------------------------------------------------------- 1. cadastro --
print("\n[1] Criar um veterinario de teste")
cod, r = pedir("POST", "/api/vets", {
    "nome": "Dra. Teste Automatizado",
    "cargo": "Médica-Veterinária",
    "especialidade": "Cardiologia",
    "crmv": "CRMV-DF 9999",
    "cidade": "Águas Claras - DF",
    "descricao": "Biografia de teste com acento: coração, atenção.",
    "areas": ["Ecocardiograma", "Consulta cardiológica"],
    "status": "ativo",
    "fotoNova": png_de_teste(),
})
checa("cadastro criado", cod == 200 and r.get("ok"), str(r)[:120])
novo = r.get("vet", {})
slug = novo.get("slug")
vid = novo.get("id")
print("       slug gerado: %s" % slug)
checa("slug veio do nome", slug == "dra-teste-automatizado", slug)
checa("acentos preservados", "coração" in novo.get("descricao", ""))
checa("areas viraram lista", novo.get("areas") == ["Ecocardiograma", "Consulta cardiológica"])
checa("foto foi gravada", novo.get("foto", "").startswith("assets/vets/"), novo.get("foto"))
caminho_foto = os.path.join(RAIZ, "site", novo.get("foto", "x").replace("/", os.sep))
checa("arquivo da foto existe no disco", os.path.isfile(caminho_foto), caminho_foto)

# ------------------------------------------- 2. aparece para o visitante --
print("\n[2] Aparece na landing page")
cod, texto = buscar("/data/veterinarios.json")
publico = json.loads(texto)
achou = [v for v in publico if v.get("slug") == slug]
checa("esta no arquivo que o site le", len(achou) == 1)
ativos = [v for v in publico if v.get("status") != "inativo"]
checa("entra na lista de ativos", any(v["slug"] == slug for v in ativos))
checa("total subiu de %d para %d" % (total_inicial, len(publico)), len(publico) == total_inicial + 1)

# ------------------------------------------------- 3. card e modal do site --
# A landing page usa a modal do template, nao paginas separadas: o painel so
# alimenta os dados. Quem desenha continua sendo o site original.
print("\n[3] Card e modal na landing page")
cod, js = buscar("/js/vethome.js")
checa("o card abre a modal do template", "vetBackdrop" in js)
checa("o card mostra o CRMV", "crmv" in js)
checa("a modal mostra a biografia", "descricao" in js)
checa("quem esta oculto nao entra", "inativo" in js)
checa("respeita a ordem do painel", "ordem" in js)

cod, html = buscar("/index.html")
checa("a landing tem o alvo da modal", 'id="vetBackdrop"' in html)

# ----------------------------------------------------------- 4/5. edicao --
print("\n[4] Editar e ver a mudanca no site")
cod, r = pedir("POST", "/api/vets", {
    "id": vid,
    "nome": "Dra. Teste Renomeada",
    "cargo": "Médica-Veterinária",
    "especialidade": "Neurologia",
    "crmv": "CRMV-DF 8888",
    "cidade": "Taguatinga - DF",
    "descricao": "Biografia editada.",
    "areas": ["Neurologia clínica"],
    "status": "ativo",
    "slug": slug,
})
checa("edicao salva", cod == 200 and r.get("ok"), str(r)[:120])

cod, texto = buscar("/data/veterinarios.json")
publico = json.loads(texto)
editado = next((v for v in publico if v.get("slug") == slug), None)
checa("nome novo chegou ao site", editado and editado["nome"] == "Dra. Teste Renomeada")
checa("especialidade nova chegou", editado and editado["especialidade"] == "Neurologia")
checa("cidade nova chegou", editado and editado["cidade"] == "Taguatinga - DF")
checa("nao duplicou o cadastro", len(publico) == total_inicial + 1)
checa("a foto foi mantida sem reenviar", editado and editado["foto"].startswith("assets/vets/"))

# ---------------------------------------------------------- 6/7. inativo --
print("\n[6] Marcar como inativo")
cod, r = pedir("POST", "/api/vets", {
    "id": vid, "nome": "Dra. Teste Renomeada", "slug": slug,
    "status": "inativo", "especialidade": "Neurologia",
})
checa("status salvo como inativo", cod == 200)

cod, texto = buscar("/data/veterinarios.json")
publico = json.loads(texto)
oculto = next((v for v in publico if v.get("slug") == slug), None)
checa("o cadastro CONTINUA salvo", oculto is not None)
checa("mas marcado como inativo", oculto and oculto["status"] == "inativo")
ativos = [v for v in publico if v.get("status") != "inativo"]
checa("sai da lista que o site mostra", not any(v["slug"] == slug for v in ativos))
checa("os %d originais seguem ativos" % total_inicial, len(ativos) == total_inicial)

# ----------------------------------------------------------- 8. ordenacao --
print("\n[8] Reordenar")
cod, lista = pedir("GET", "/api/vets")
# guarda o valor exato de ordem de cada um, para devolver do jeito que estava.
# Restaurar por POSICAO nao serve: o cadastro de teste entra no meio da lista
# e empurra os outros.
antes_ordem = {v["id"]: v.get("ordem") for v in lista}

ids = [v["id"] for v in lista]
invertido = ids[:2][::-1] + ids[2:]
cod, r = pedir("POST", "/api/ordem", {"ids": invertido})
checa("nova ordem salva", cod == 200)
cod, texto = buscar("/data/veterinarios.json")
depois = json.loads(texto)
checa("a ordem mudou no arquivo do site",
      [v["id"] for v in depois][:2] == invertido[:2],
      str([v["id"] for v in depois][:2]))

# devolve os valores originais, um por um
with io.open(DADOS, encoding="utf-8") as f:
    atual = json.load(f)
for v in atual:
    if v["id"] in antes_ordem:
        v["ordem"] = antes_ordem[v["id"]]
atual.sort(key=lambda v: v.get("ordem") or 0)
with io.open(DADOS, "w", encoding="utf-8") as f:
    json.dump(atual, f, ensure_ascii=False, indent=2)
    f.write(chr(10))
cod, texto = buscar("/data/veterinarios.json")
checa("ordem original devolvida",
      [v["id"] for v in json.loads(texto)] == ids, "")

# ------------------------------------------------------------- limpeza ----
print("\n[9] Limpeza do cadastro de teste")
with io.open(DADOS, encoding="utf-8") as f:
    atuais = json.load(f)
restantes = [v for v in atuais if v.get("slug") != slug]
with io.open(DADOS, "w", encoding="utf-8") as f:
    json.dump(restantes, f, ensure_ascii=False, indent=2)
    f.write("\n")
if os.path.isfile(caminho_foto):
    os.remove(caminho_foto)
cod, texto = buscar("/data/veterinarios.json")
checa("site voltou aos %d originais" % total_inicial, len(json.loads(texto)) == total_inicial)

print("\n" + "=" * 62)
if falhas:
    print("%d de %d verificacoes FALHARAM:" % (len(falhas), passos))
    for f in falhas:
        print("   - " + f)
    sys.exit(1)
print("TODAS as %d verificacoes passaram" % passos)
