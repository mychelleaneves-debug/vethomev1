# -*- coding: utf-8 -*-
"""Teste da operacao da clinica, do login ate o encaixe confirmado.

Roda contra o servidor em 127.0.0.1:8791. Nao inventa veterinario: usa os que
ja estao cadastrados. Guarda a pasta dados/ inteira antes de comecar e devolve
como estava no fim, entao pode rodar mesmo com agenda de verdade la dentro.
"""
import io
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from http.cookiejar import CookieJar

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8791"
SENHA = "senha-de-teste-vethome"
EU = "Teste Automatizado"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.path.join(RAIZ, "dados")
GUARDADO = os.path.join(RAIZ, "dados-guardado-pelo-teste")

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
        texto = e.read().decode("utf-8")
        try:
            return e.code, json.loads(texto)
        except ValueError:
            return e.code, {"erro": texto}


def guardar_dados():
    if os.path.exists(GUARDADO):
        shutil.rmtree(GUARDADO)
    if os.path.exists(DADOS):
        shutil.copytree(DADOS, GUARDADO)
    else:
        os.makedirs(GUARDADO)


def devolver_dados():
    if os.path.exists(DADOS):
        shutil.rmtree(DADOS)
    if os.path.exists(GUARDADO):
        shutil.copytree(GUARDADO, DADOS)
        shutil.rmtree(GUARDADO)


def ler_arquivo(nome):
    caminho = os.path.join(DADOS, nome)
    if not os.path.exists(caminho):
        return []
    with io.open(caminho, encoding="utf-8") as f:
        return json.load(f)


print("=" * 64)
print("TESTE DA OPERACAO DA CLINICA")
print("=" * 64)

guardar_dados()
try:
    # ------------------------------------------------------------ 0. login --
    print("\n[0] Acesso")
    cod, _ = pedir("GET", "/api/op/atendimentos")
    checa("sem senha, a operacao recusa (401)", cod == 401, "veio %s" % cod)

    cod, r = pedir("POST", "/api/login", {"senha": SENHA, "quem": EU})
    checa("login com o nome de quem entra", cod == 200 and r.get("ok"), str(r))

    cod, s = pedir("GET", "/api/sessao")
    checa("a sessao lembra quem entrou", s.get("quem") == EU, str(s.get("quem")))
    checa("a operacao tem onde guardar", s.get("operacao") is True, str(s))

    cod, inicio = pedir("GET", "/api/op/inicio")
    checa("os veterinarios do site alimentam a operacao",
          cod == 200 and len(inicio.get("vets", [])) > 0,
          "%d vets" % len(inicio.get("vets", [])))
    vets = inicio["vets"]
    vet = vets[0]
    outro = vets[1] if len(vets) > 1 else vets[0]
    print("       usando %s" % vet["nome"])
    checa("nao ha cadastro paralelo de vet: o id vem do site",
          "-" in vet["id"], vet["id"])

    # ------------------------------------------------- 1. disponibilidade --
    print("\n[1] Disponibilidade")
    # segunda a sexta, manha e tarde
    semana = {}
    for dia in ("1", "2", "3", "4", "5"):
        semana[dia] = [{"inicio": "08:00", "fim": "12:00"},
                       {"inicio": "14:00", "fim": "18:00"}]
    cod, r = pedir("POST", "/api/op/disponibilidade",
                   {"vetId": vet["id"], "duracaoPadrao": 60, "semana": semana})
    checa("disponibilidade salva", cod == 200 and r.get("ok"), str(r)[:120])

    cod, r = pedir("POST", "/api/op/disponibilidade",
                   {"vetId": vet["id"], "duracaoPadrao": 60,
                    "semana": {"1": [{"inicio": "08:00", "fim": "12:00"},
                                     {"inicio": "11:00", "fim": "13:00"}]}})
    checa("periodos que se sobrepoem sao recusados", cod == 400, "veio %s" % cod)
    checa("a recusa explica o problema", "sobrep" in str(r.get("erro", "")).lower(),
          str(r.get("erro")))

    pedir("POST", "/api/op/disponibilidade",
          {"vetId": vet["id"], "duracaoPadrao": 60, "semana": semana})

    cod, lista = pedir("GET", "/api/op/disponibilidade")
    minha = next((d for d in lista if d["vetId"] == vet["id"]), None)
    checa("a semana foi guardada", minha and len(minha["semana"]) == 5)
    checa("duracao padrao guardada", minha and minha["duracaoPadrao"] == 60)

    # ---------------------------------------------------- 2. agendamento --
    print("\n[2] Agendamento dentro da disponibilidade")
    # proxima terca-feira, para cair sempre num dia util configurado
    hoje = date.fromisoformat(inicio["hoje"])
    terca = hoje + timedelta(days=(1 - hoje.weekday()) % 7 or 7)
    dia = terca.isoformat()
    print("       dia escolhido: %s (%s)" % (dia, terca.strftime("%A")))

    base = {"paciente": "Thor", "tutor": "Karoline", "contato": "61999990000",
            "vetId": vet["id"], "tipo": "Consulta", "data": dia,
            "inicio": "09:00", "duracao": 60, "status": "agendado",
            "observacoes": "Primeira consulta. Acentuação preservada?"}

    cod, r = pedir("POST", "/api/op/atendimento", dict(base))
    checa("atendimento criado", cod == 200 and r.get("ok"), str(r)[:160])
    at = r.get("atendimento", {})
    id_thor = at.get("id")
    checa("fim calculado a partir da duracao", at.get("fim") == "10:00", at.get("fim"))
    checa("acentos preservados", "Acentuação" in at.get("observacoes", ""))
    checa("registra quem criou", at.get("criadoPor") == EU, at.get("criadoPor"))

    # ------------------------------------------------------ 3. conflitos --
    print("\n[3] Conflitos - o servidor precisa barrar")
    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Mel", inicio="09:30"))
    checa("dois atendimentos no mesmo horario: barrado", cod == 409, "veio %s" % cod)
    checa("diz que o horario ja tem atendimento",
          any("já possui atendimento" in c for c in r.get("conflitos", [])),
          str(r.get("conflitos")))

    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Nina", inicio="19:00"))
    checa("fora da disponibilidade: barrado", cod == 409, "veio %s" % cod)
    checa("diz qual e a faixa do dia",
          any("Fora da disponibilidade" in c for c in r.get("conflitos", [])),
          str(r.get("conflitos")))

    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Nina", data=(terca + timedelta(days=5)).isoformat()))
    checa("dia em que o vet nao atende: barrado", cod == 409, "veio %s" % cod)

    cod, r = pedir("POST", "/api/op/atendimento", dict(base, paciente="Nina", inicio="9h"))
    checa("horario mal escrito: recusado com explicacao", cod == 400, "veio %s" % cod)

    # ------------------------------------------------------ 4. bloqueio --
    print("\n[4] Bloqueio de horario")
    cod, r = pedir("POST", "/api/op/bloqueio",
                   {"vetId": vet["id"], "data": dia, "inicio": "14:00",
                    "fim": "15:00", "motivo": "Reunião",
                    "observacao": "Alinhamento da equipe"})
    checa("bloqueio criado", cod == 200 and r.get("ok"), str(r)[:120])
    id_bloqueio = r.get("bloqueio", {}).get("id")

    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Nina", inicio="14:00"))
    checa("agendar dentro do bloqueio: barrado", cod == 409, "veio %s" % cod)
    checa("diz qual e o bloqueio",
          any("Reunião" in c for c in r.get("conflitos", [])), str(r.get("conflitos")))

    cod, livres = pedir("GET", "/api/op/horarios?vet=%s&data=%s" % (vet["id"], dia))
    checa("horarios livres nao oferecem o bloqueado", "14:00" not in livres, str(livres))
    checa("horarios livres nao oferecem o ja ocupado", "09:00" not in livres, str(livres))
    checa("horarios livres oferecem o resto", "15:00" in livres, str(livres))

    # -------------------------------------------------------- 5. ferias --
    print("\n[5] Férias")
    cod, r = pedir("POST", "/api/op/ausencia",
                   {"vetId": outro["id"], "tipo": "ferias",
                    "inicio": dia, "fim": (terca + timedelta(days=10)).isoformat(),
                    "observacao": "Férias programadas"})
    checa("ferias cadastradas", cod == 200 and r.get("ok"), str(r)[:120])
    id_ferias = r.get("ausencia", {}).get("id")

    pedir("POST", "/api/op/disponibilidade",
          {"vetId": outro["id"], "duracaoPadrao": 60, "semana": semana})
    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Cacau", vetId=outro["id"], inicio="09:00"))
    checa("agendar durante as ferias: barrado", cod == 409, "veio %s" % cod)
    checa("diz que esta de ferias",
          any("férias" in c for c in r.get("conflitos", [])), str(r.get("conflitos")))

    # -------------------------------------------------------- 6. encaixe --
    print("\n[6] Encaixe")
    encaixe = dict(base, paciente="Pipa", inicio="09:30", encaixe=True,
                   motivoEncaixe="Urgência: vômito desde ontem")
    cod, r = pedir("POST", "/api/op/atendimento", dict(encaixe))
    checa("encaixe sem confirmar: nao salva", cod == 409, "veio %s" % cod)
    checa("oferece confirmar o encaixe", r.get("podeEncaixar") is True, str(r))

    cod, r = pedir("POST", "/api/op/atendimento", dict(encaixe, confirmado=True))
    checa("encaixe confirmado: salva", cod == 200 and r.get("ok"), str(r)[:160])
    at_encaixe = r.get("atendimento", {})
    id_pipa = at_encaixe.get("id")
    checa("fica marcado como encaixe", at_encaixe.get("encaixe") is True)
    checa("guarda o motivo do encaixe",
          "Urgência" in at_encaixe.get("motivoEncaixe", ""), at_encaixe.get("motivoEncaixe"))
    checa("devolve o aviso do conflito aceito", len(r.get("avisos", [])) > 0, str(r.get("avisos")))

    agenda = ler_arquivo("atendimentos.json")
    thor = next((a for a in agenda if a["id"] == id_thor), None)
    checa("o encaixe nao mexeu no atendimento que ja existia",
          thor and thor["inicio"] == "09:00" and thor["status"] == "agendado")

    # ------------------------------------------------------- 7. status ----
    print("\n[7] Status e reagendamento")
    cod, r = pedir("POST", "/api/op/atendimento/status",
                   {"id": id_thor, "status": "realizado"})
    checa("marcar como realizado", cod == 200 and
          r.get("atendimento", {}).get("status") == "realizado", str(r)[:120])

    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, id=id_pipa, paciente="Pipa", inicio="16:00",
                        encaixe=True, confirmado=True, status="agendado"))
    checa("reagendar para outro horario", cod == 200 and
          r.get("atendimento", {}).get("inicio") == "16:00", str(r)[:120])

    # -------------------------------------------------- 8. cancelamento --
    print("\n[8] Cancelamento")
    cod, r = pedir("POST", "/api/op/atendimento/cancelar",
                   {"id": id_pipa, "motivo": "Cliente cancelou",
                    "observacao": "Ligou avisando"})
    checa("cancelamento aceito", cod == 200 and r.get("ok"), str(r)[:120])
    cancelado = r.get("atendimento", {})
    checa("o registro NAO foi apagado", cancelado.get("id") == id_pipa)
    checa("status virou cancelado", cancelado.get("status") == "cancelado")
    checa("guarda o motivo", cancelado.get("motivoCancelamento") == "Cliente cancelou")
    checa("guarda quem cancelou", cancelado.get("canceladoPor") == EU)
    checa("guarda quando cancelou", bool(cancelado.get("canceladoEm")))

    cod, r = pedir("POST", "/api/op/atendimento/cancelar",
                   {"id": id_pipa, "motivo": "Outro"})
    checa("nao deixa cancelar duas vezes", cod == 400, "veio %s" % cod)

    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Pipa", inicio="09:30",
                        reagendadoDe=id_pipa, encaixe=True, confirmado=True))
    checa("o horario cancelado libera espaco", cod == 200, str(r)[:120])
    id_remarcado = r.get("atendimento", {}).get("id")
    checa("guarda de qual atendimento veio",
          r.get("atendimento", {}).get("reagendadoDe") == id_pipa)

    # -------------------------------------------------------- 9. escala --
    print("\n[9] Escala")
    cod, esc = pedir("GET", "/api/op/escala?data=" + dia)
    checa("escala sai da disponibilidade sozinha", cod == 200 and esc.get("derivada") is True)
    nomes_na_escala = [v["nome"] for t in esc.get("turnos", []) for v in t["vets"]]
    checa("quem tem disponibilidade aparece", vet["nome"] in nomes_na_escala,
          str(nomes_na_escala)[:120])
    checa("quem esta de ferias nao aparece", outro["nome"] not in nomes_na_escala,
          str(nomes_na_escala)[:120])
    checa("mas aparece na lista de ausentes",
          any(a["nome"] == outro["nome"] for a in esc.get("ausentes", [])),
          str(esc.get("ausentes")))
    checa("o bloqueio do dia aparece na escala", len(esc.get("bloqueios", [])) == 1)

    cod, r = pedir("POST", "/api/op/escala",
                   {"data": dia, "observacao": "Plantão reforçado",
                    "turnos": [{"inicio": "08:00", "fim": "12:00",
                                "vets": [{"vetId": vet["id"], "nome": vet["nome"]}]}]})
    checa("escala ajustada a mao salva", cod == 200 and r.get("ok"), str(r)[:120])

    cod, esc = pedir("GET", "/api/op/escala?data=" + dia)
    checa("o ajuste manual manda", esc.get("derivada") is False)
    checa("e a tela sabe que foi ajustado", esc.get("observacao") == "Plantão reforçado")

    cod, r = pedir("POST", "/api/op/escala/remover", {"data": dia})
    checa("remover o ajuste volta para a disponibilidade", cod == 200)
    cod, esc = pedir("GET", "/api/op/escala?data=" + dia)
    checa("e volta mesmo", esc.get("derivada") is True)

    cod, semana_esc = pedir("GET", "/api/op/escala-semana?data=" + dia)
    checa("escala da semana traz sete dias", len(semana_esc) == 7, str(len(semana_esc)))

    # ------------------------------------------------------ 10. resumo ----
    print("\n[10] Painel da operação")
    cod, res = pedir("GET", "/api/op/resumo")
    checa("resumo responde", cod == 200 and "cards" in res, str(res)[:120])
    checa("tem os contadores do dia",
          set(["atendimentos", "confirmados", "pendentes", "encaixes", "cancelados"])
          <= set(res["cards"].keys()), str(res.get("cards")))
    checa("lista os proximos atendimentos", isinstance(res.get("proximos"), list))
    checa("lista quem esta fora hoje", isinstance(res.get("indisponiveis"), list))

    # --------------------------------------------------- 11. auditoria ----
    print("\n[11] Histórico")
    cod, log = pedir("GET", "/api/op/auditoria")
    acoes = [l["acao"] for l in log]
    for esperada in ("atendimento.criado", "encaixe.criado", "atendimento.cancelado",
                     "atendimento.reagendado", "bloqueio.criado", "ausencia.salva",
                     "disponibilidade.alterada", "escala.alterada"):
        checa("registrou %s" % esperada, esperada in acoes, str(sorted(set(acoes))))
    # o historico vem do mais novo para o mais antigo, e este teste acabou de
    # rodar - entao o primeiro registro de cada acao tem que ser dele. Exigir
    # isso do historico INTEIRO daria falso negativo se a pasta ja tivesse uso.
    recentes = {}
    for l in log:
        recentes.setdefault(l["acao"], l)
    checa("o historico diz quem fez",
          all(recentes[a]["quem"] == EU for a in
              ("atendimento.criado", "atendimento.cancelado", "bloqueio.criado")),
          str({a: recentes[a]["quem"] for a in recentes}))

    # --------------------------------------------------- 12. limpeza -----
    print("\n[12] Remoção de bloqueio e férias")
    cod, r = pedir("POST", "/api/op/bloqueio/remover", {"id": id_bloqueio})
    checa("bloqueio removido", cod == 200, str(r)[:80])
    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Nina", inicio="14:00"))
    checa("o horario volta a aceitar agendamento", cod == 200, str(r)[:120])

    cod, r = pedir("POST", "/api/op/ausencia/remover", {"id": id_ferias})
    checa("ferias removidas", cod == 200, str(r)[:80])
    cod, r = pedir("POST", "/api/op/atendimento",
                   dict(base, paciente="Cacau", vetId=outro["id"], inicio="11:00"))
    checa("o vet volta a poder atender", cod == 200, str(r)[:120])

finally:
    devolver_dados()
    print("\n(pasta dados/ devolvida como estava antes do teste)")

print("\n" + "=" * 64)
if falhas:
    print("%d de %d verificacoes FALHARAM:" % (len(falhas), passos))
    for f in falhas:
        print("   - " + f)
    sys.exit(1)
print("TODAS as %d verificacoes passaram" % passos)
