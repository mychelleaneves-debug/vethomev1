# -*- coding: utf-8 -*-
"""Operacao da clinica: agenda, disponibilidade, ausencias, bloqueios, escala.

Tudo gira em torno do veterinario que ja existe em veterinarios.json. Nao ha
cadastro paralelo de equipe: o vetId daqui e o id de la.

    VETERINARIO
        |
        +-- DISPONIBILIDADE   horarios que se repetem toda semana
        +-- AUSENCIAS         ferias, folgas, ausencias (dias inteiros)
        +-- BLOQUEIOS         buracos pontuais num dia (reuniao, almoco...)
        |
        +-- ESCALA            quem trabalha em cada dia. Sai sozinha da
        |                     disponibilidade menos as ausencias; so vira
        |                     registro proprio quando alguem edita a mao.
        |
        +-- AGENDA            os atendimentos, validados contra tudo acima

As tres primeiras dizem QUANDO o veterinario pode atender. A agenda so aceita
um horario que passe pelas quatro checagens - a nao ser que seja encaixe, e
ai exige confirmacao explicita de quem esta marcando.

Nada aqui apaga registro: cancelar muda o status e guarda motivo, data e
autor. O historico fica em auditoria.json.
"""
import re
import secrets
from datetime import date, datetime, timedelta

from armazenamento import ErroDeArmazenamento

# ------------------------------------------------------------ constantes --
ARQ_ATENDIMENTOS = "atendimentos.json"
ARQ_PACIENTES = "pacientes.json"
ARQ_DISPONIBILIDADE = "disponibilidade.json"
ARQ_BLOQUEIOS = "bloqueios.json"
ARQ_AUSENCIAS = "ausencias.json"
ARQ_ESCALAS = "escalas.json"
ARQ_AUDITORIA = "auditoria.json"

TIPOS_ATENDIMENTO = [
    "Consulta", "Retorno", "Vacinação", "Coleta de exames",
    "Ultrassonografia", "Cirurgia", "Fisioterapia",
    "Orientação nutricional", "Outro",
]

# "encaixe" nao entra aqui de proposito: um encaixe tambem precisa poder ser
# confirmado, realizado ou cancelado. Ele e uma marca no atendimento, nao um
# estado que substitui os outros.
STATUS = ["agendado", "confirmado", "em_atendimento", "realizado",
          "cancelado", "faltou"]

STATUS_ROTULO = {
    "agendado": "Agendado", "confirmado": "Confirmado",
    "em_atendimento": "Em atendimento", "realizado": "Realizado",
    "cancelado": "Cancelado", "faltou": "Faltou",
}

MOTIVOS_CANCELAMENTO = [
    "Cliente cancelou", "Veterinário indisponível", "Clínica cancelou",
    "Reagendamento", "Outro",
]

MOTIVOS_BLOQUEIO = [
    "Reunião", "Manutenção", "Treinamento", "Evento",
    "Horário reservado", "Almoço", "Outro",
]

TIPOS_AUSENCIA = ["ferias", "folga", "ausencia"]
AUSENCIA_ROTULO = {"ferias": "Férias", "folga": "Folga", "ausencia": "Ausência"}

DIAS = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"]

DURACAO_PADRAO = 40          # minutos
LIMITE_AUDITORIA = 3000      # registros guardados


# ------------------------------------------------------------- utilidades --
def agora():
    return datetime.now().replace(microsecond=0).isoformat(" ")


def novo_id(prefixo):
    return prefixo + "-" + secrets.token_hex(5)


def em_minutos(hora):
    """"08:30" -> 510. Erra alto: horario invalido nao pode virar agendamento."""
    m = re.match(r"^([01]?\d|2[0-3]):([0-5]\d)$", str(hora or "").strip())
    if not m:
        raise ValueError("Horário inválido: %s. Use o formato 08:30." % hora)
    return int(m.group(1)) * 60 + int(m.group(2))


def em_hora(minutos):
    minutos = max(0, min(24 * 60, int(minutos)))
    return "%02d:%02d" % (minutos // 60, minutos % 60)


def como_data(valor, rotulo="data"):
    try:
        return date.fromisoformat(str(valor or "").strip())
    except ValueError:
        raise ValueError("A %s precisa estar no formato 2026-09-01." % rotulo)


def texto(v, limite=2000):
    return str(v if v is not None else "").strip()[:limite]


def cruzam(inicio_a, fim_a, inicio_b, fim_b):
    """Dois periodos se sobrepoem? Encostar nao conta: 09:00-10:00 e
    10:00-11:00 convivem em paz."""
    return inicio_a < fim_b and inicio_b < fim_a


# ------------------------------------------------------------- colecoes ---
def _ler(arm, arquivo):
    if arm is None:
        raise ErroDeArmazenamento(
            "A operação da clínica ainda não tem onde guardar os dados. "
            "Falta configurar o repositório privado (GITHUB_REPO_DADOS).")
    dados = arm.ler_arquivo(arquivo, padrao=[])
    return dados if isinstance(dados, list) else []


def _gravar(arm, arquivo, dados, mensagem):
    if arm is None:
        raise ErroDeArmazenamento(
            "A operação da clínica ainda não tem onde guardar os dados. "
            "Falta configurar o repositório privado (GITHUB_REPO_DADOS).")
    arm.gravar_arquivo(arquivo, dados, mensagem)


def registrar(arm, quem, acao, resumo):
    """Historico do que foi feito. Nunca impede a acao principal: se o log
    falhar, o agendamento ja foi salvo e nao vale desfazer por causa disso."""
    try:
        historico = _ler(arm, ARQ_AUDITORIA)
        historico.append({
            "id": novo_id("log"),
            "quando": agora(),
            "quem": texto(quem) or "não identificado",
            "acao": acao,
            "resumo": texto(resumo, 300),
        })
        _gravar(arm, ARQ_AUDITORIA, historico[-LIMITE_AUDITORIA:],
                "Historico: " + acao)
    except Exception:
        pass


# ====================================================== DISPONIBILIDADE ====
def listar_disponibilidade(arm):
    return _ler(arm, ARQ_DISPONIBILIDADE)


def disponibilidade_do_vet(lista, vet_id):
    for d in lista:
        if d.get("vetId") == vet_id:
            return d
    return {"vetId": vet_id, "duracaoPadrao": DURACAO_PADRAO, "semana": {}}


def _normalizar_periodos(bruto):
    """Limpa, valida e junta os periodos de um dia."""
    limpos = []
    for p in (bruto or []):
        inicio = em_minutos(p.get("inicio"))
        fim = em_minutos(p.get("fim"))
        if fim <= inicio:
            raise ValueError("O fim (%s) precisa vir depois do início (%s)."
                             % (p.get("fim"), p.get("inicio")))
        limpos.append([inicio, fim])
    limpos.sort()

    for anterior, seguinte in zip(limpos, limpos[1:]):
        if seguinte[0] < anterior[1]:
            raise ValueError("Os períodos %s-%s e %s-%s se sobrepõem."
                             % (em_hora(anterior[0]), em_hora(anterior[1]),
                                em_hora(seguinte[0]), em_hora(seguinte[1])))
    return [{"inicio": em_hora(a), "fim": em_hora(b)} for a, b in limpos]


def salvar_disponibilidade(arm, vet_id, dados, quem):
    vet_id = texto(vet_id)
    if not vet_id:
        raise ValueError("Escolha o veterinário.")

    try:
        duracao = int(dados.get("duracaoPadrao") or DURACAO_PADRAO)
    except (TypeError, ValueError):
        duracao = DURACAO_PADRAO
    if not 5 <= duracao <= 480:
        raise ValueError("A duração padrão precisa ficar entre 5 e 480 minutos.")

    semana = {}
    for dia in range(7):
        periodos = _normalizar_periodos((dados.get("semana") or {}).get(str(dia)))
        if periodos:
            semana[str(dia)] = periodos

    lista = listar_disponibilidade(arm)
    registro = {"vetId": vet_id, "duracaoPadrao": duracao, "semana": semana,
                "atualizadoEm": agora(), "atualizadoPor": texto(quem)}
    lista = [d for d in lista if d.get("vetId") != vet_id] + [registro]
    _gravar(arm, ARQ_DISPONIBILIDADE, lista, "Disponibilidade de " + vet_id)
    registrar(arm, quem, "disponibilidade.alterada",
              "Disponibilidade de %s atualizada" % vet_id)
    return registro


# ============================================================= AUSENCIAS ===
def listar_ausencias(arm):
    return sorted(_ler(arm, ARQ_AUSENCIAS), key=lambda a: a.get("inicio", ""))


def salvar_ausencia(arm, dados, quem):
    vet_id = texto(dados.get("vetId"))
    if not vet_id:
        raise ValueError("Escolha o veterinário.")

    tipo = dados.get("tipo")
    if tipo not in TIPOS_AUSENCIA:
        raise ValueError("Escolha férias, folga ou ausência.")

    inicio = como_data(dados.get("inicio"), "data inicial")
    fim = como_data(dados.get("fim"), "data final")
    if fim < inicio:
        raise ValueError("A data final não pode ser antes da inicial.")

    lista = listar_ausencias(arm)
    ident = texto(dados.get("id")) or novo_id("aus")
    registro = {
        "id": ident, "vetId": vet_id, "tipo": tipo,
        "inicio": inicio.isoformat(), "fim": fim.isoformat(),
        "observacao": texto(dados.get("observacao"), 500),
        "criadoPor": texto(quem), "criadoEm": agora(),
    }
    lista = [a for a in lista if a.get("id") != ident] + [registro]
    _gravar(arm, ARQ_AUSENCIAS, lista, "Ausencia de " + vet_id)
    registrar(arm, quem, "ausencia.salva",
              "%s de %s: %s a %s" % (AUSENCIA_ROTULO[tipo], vet_id,
                                     registro["inicio"], registro["fim"]))
    return registro


def remover_ausencia(arm, ident, quem):
    lista = listar_ausencias(arm)
    alvo = next((a for a in lista if a.get("id") == ident), None)
    if not alvo:
        raise ValueError("Esse período não existe mais.")
    _gravar(arm, ARQ_AUSENCIAS, [a for a in lista if a.get("id") != ident],
            "Remove ausencia")
    registrar(arm, quem, "ausencia.removida",
              "%s de %s removida" % (AUSENCIA_ROTULO.get(alvo.get("tipo"), "Ausência"),
                                     alvo.get("vetId")))


def ausencia_no_dia(ausencias, vet_id, dia):
    """A ausencia que pega este dia, se houver."""
    for a in ausencias:
        if a.get("vetId") != vet_id:
            continue
        try:
            if date.fromisoformat(a["inicio"]) <= dia <= date.fromisoformat(a["fim"]):
                return a
        except (KeyError, ValueError):
            continue
    return None


# ============================================================= BLOQUEIOS ===
def listar_bloqueios(arm):
    return sorted(_ler(arm, ARQ_BLOQUEIOS),
                  key=lambda b: (b.get("data", ""), b.get("inicio", "")))


def salvar_bloqueio(arm, dados, quem):
    dia = como_data(dados.get("data"))
    inicio = em_minutos(dados.get("inicio"))
    fim = em_minutos(dados.get("fim"))
    if fim <= inicio:
        raise ValueError("A hora final precisa vir depois da inicial.")

    motivo = texto(dados.get("motivo")) or "Horário reservado"

    lista = listar_bloqueios(arm)
    ident = texto(dados.get("id")) or novo_id("blo")
    registro = {
        "id": ident,
        # vazio = vale para a clinica inteira
        "vetId": texto(dados.get("vetId")),
        "data": dia.isoformat(), "inicio": em_hora(inicio), "fim": em_hora(fim),
        "motivo": motivo, "observacao": texto(dados.get("observacao"), 500),
        "criadoPor": texto(quem), "criadoEm": agora(),
    }
    lista = [b for b in lista if b.get("id") != ident] + [registro]
    _gravar(arm, ARQ_BLOQUEIOS, lista, "Bloqueio em " + registro["data"])
    registrar(arm, quem, "bloqueio.criado",
              "%s em %s das %s as %s" % (motivo, registro["data"],
                                         registro["inicio"], registro["fim"]))
    return registro


def remover_bloqueio(arm, ident, quem):
    lista = listar_bloqueios(arm)
    alvo = next((b for b in lista if b.get("id") == ident), None)
    if not alvo:
        raise ValueError("Esse bloqueio não existe mais.")
    _gravar(arm, ARQ_BLOQUEIOS, [b for b in lista if b.get("id") != ident],
            "Remove bloqueio")
    registrar(arm, quem, "bloqueio.removido",
              "%s em %s removido" % (alvo.get("motivo"), alvo.get("data")))


def bloqueios_do_dia(bloqueios, vet_id, dia):
    iso = dia.isoformat()
    return [b for b in bloqueios
            if b.get("data") == iso and b.get("vetId") in ("", None, vet_id)]


# ============================================================= PACIENTES ===
def listar_pacientes(arm):
    return sorted(_ler(arm, ARQ_PACIENTES), key=lambda p: p.get("nome", "").lower())


def salvar_paciente(arm, dados, quem):
    nome = texto(dados.get("nome"), 120)
    if not nome:
        raise ValueError("O nome do pet é obrigatório.")
    tutor = texto(dados.get("tutor"), 120)
    if not tutor:
        raise ValueError("O nome do tutor é obrigatório.")

    lista = listar_pacientes(arm)
    ident = texto(dados.get("id")) or novo_id("pac")
    registro = {
        "id": ident, "nome": nome, "tutor": tutor,
        "especie": texto(dados.get("especie"), 40),
        "raca": texto(dados.get("raca"), 60),
        "telefone": texto(dados.get("telefone"), 40),
        "endereco": texto(dados.get("endereco"), 200),
        "observacoes": texto(dados.get("observacoes"), 1500),
        "criadoEm": agora(),
    }
    anterior = next((p for p in lista if p.get("id") == ident), None)
    if anterior:
        registro["criadoEm"] = anterior.get("criadoEm", registro["criadoEm"])
    lista = [p for p in lista if p.get("id") != ident] + [registro]
    _gravar(arm, ARQ_PACIENTES, lista, "Paciente " + nome)
    registrar(arm, quem, "paciente.salvo", "%s (tutor: %s)" % (nome, tutor))
    return registro


# ================================================================ AGENDA ===
def listar_atendimentos(arm):
    return sorted(_ler(arm, ARQ_ATENDIMENTOS),
                  key=lambda a: (a.get("data", ""), a.get("inicio", "")))


def _vet_ativo(vets, vet_id):
    for v in vets:
        if v.get("id") == vet_id:
            return v
    return None


def conflitos(arm, vets, dados, ignorar_id=None, cache=None):
    """Tudo que impede este atendimento de existir, em portugues.

    Devolve uma lista de frases. Vazia = horario livre. Nao decide o que
    fazer com elas: quem chama e que sabe se e agendamento normal (barra) ou
    encaixe (avisa e pede confirmacao).
    """
    problemas = []

    vet_id = texto(dados.get("vetId"))
    vet = _vet_ativo(vets, vet_id)
    if not vet:
        return ["Escolha um veterinário da equipe."]
    nome_vet = vet.get("nome", vet_id)

    dia = como_data(dados.get("data"))
    inicio = em_minutos(dados.get("inicio"))
    fim = em_minutos(dados.get("fim"))

    # lista vazia e resposta valida: usar "or" aqui faria reler tudo de novo,
    # e em modo GitHub cada leitura e uma chamada de rede
    cache = cache if cache is not None else {}
    agenda = cache["agenda"] if "agenda" in cache else listar_atendimentos(arm)
    disponibilidade = cache["disp"] if "disp" in cache else listar_disponibilidade(arm)
    ausencias = cache["aus"] if "aus" in cache else listar_ausencias(arm)
    bloqueios = cache["blo"] if "blo" in cache else listar_bloqueios(arm)

    # 1. outro atendimento do mesmo veterinario no mesmo horario
    iso = dia.isoformat()
    for a in agenda:
        if a.get("id") == ignorar_id or a.get("vetId") != vet_id:
            continue
        if a.get("data") != iso or a.get("status") == "cancelado":
            continue
        try:
            if cruzam(inicio, fim, em_minutos(a.get("inicio")), em_minutos(a.get("fim"))):
                problemas.append(
                    "Este horário já possui atendimento: %s às %s, %s."
                    % (a.get("paciente") or "paciente", a.get("inicio"),
                       a.get("tipo") or "atendimento"))
        except ValueError:
            continue

    # 2. ferias, folga ou ausencia
    fora = ausencia_no_dia(ausencias, vet_id, dia)
    if fora:
        problemas.append("%s está de %s de %s até %s."
                         % (nome_vet, AUSENCIA_ROTULO[fora["tipo"]].lower(),
                            _dia_br(fora["inicio"]), _dia_br(fora["fim"])))

    # 3. bloqueio pontual
    for b in bloqueios_do_dia(bloqueios, vet_id, dia):
        try:
            if cruzam(inicio, fim, em_minutos(b.get("inicio")), em_minutos(b.get("fim"))):
                onde = "a clínica" if not b.get("vetId") else nome_vet
                problemas.append("Há um bloqueio para %s: %s, das %s às %s."
                                 % (onde, b.get("motivo"), b.get("inicio"), b.get("fim")))
        except ValueError:
            continue

    # 4. fora da disponibilidade da semana
    janelas = disponibilidade_do_vet(disponibilidade, vet_id)["semana"].get(
        str((dia.weekday() + 1) % 7), [])
    if not janelas:
        problemas.append("%s não atende %s. Em %s não há atendimento."
                         % (nome_vet, _dia_da_semana(dia), _dia_br(dia.isoformat())))
    else:
        cabe = any(em_minutos(j["inicio"]) <= inicio and fim <= em_minutos(j["fim"])
                   for j in janelas)
        if not cabe:
            faixas = ", ".join(j["inicio"] + "-" + j["fim"] for j in janelas)
            problemas.append(
                "Fora da disponibilidade de %s em %s (%s), quando o "
                "atendimento é das %s."
                % (nome_vet, _dia_br(dia.isoformat()), _dia_da_semana(dia), faixas))

    return problemas


def _dia_da_semana(dia):
    """"segunda-feira", "sabado" - o sufixo so vale de segunda a sexta."""
    indice = (dia.weekday() + 1) % 7
    nome = DIAS[indice].lower()
    return nome + "-feira" if indice not in (0, 6) else nome


def _dia_br(iso):
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return iso


def salvar_atendimento(arm, vets, dados, quem):
    """Cria ou edita. Devolve (registro, avisos).

    Se houver conflito e nao for encaixe, levanta erro com a lista.
    Se for encaixe, exige dados["confirmado"] == True para passar.
    """
    ident = texto(dados.get("id"))
    agenda = listar_atendimentos(arm)
    anterior = next((a for a in agenda if a.get("id") == ident), None) if ident else None

    paciente = texto(dados.get("paciente"), 120)
    if not paciente:
        raise ValueError("Informe o nome do paciente.")
    tutor = texto(dados.get("tutor"), 120)
    if not tutor:
        raise ValueError("Informe o nome do tutor.")

    tipo = texto(dados.get("tipo")) or "Consulta"
    if tipo not in TIPOS_ATENDIMENTO:
        raise ValueError("Tipo de atendimento desconhecido: %s." % tipo)

    status = dados.get("status") or "agendado"
    if status not in STATUS:
        raise ValueError("Status desconhecido: %s." % status)

    dia = como_data(dados.get("data"))
    inicio = em_minutos(dados.get("inicio"))
    try:
        duracao = int(dados.get("duracao") or DURACAO_PADRAO)
    except (TypeError, ValueError):
        duracao = DURACAO_PADRAO
    if not 5 <= duracao <= 600:
        raise ValueError("A duração precisa ficar entre 5 e 600 minutos.")
    fim = inicio + duracao
    if fim > 24 * 60:
        raise ValueError("O atendimento passaria da meia-noite.")

    encaixe = bool(dados.get("encaixe"))
    proposta = {"vetId": texto(dados.get("vetId")), "data": dia.isoformat(),
                "inicio": em_hora(inicio), "fim": em_hora(fim)}

    avisos = []
    if status != "cancelado":
        problemas = conflitos(arm, vets, proposta, ignorar_id=ident or None)
        if problemas:
            if not encaixe:
                raise ConflitoDeAgenda(problemas)
            if not dados.get("confirmado"):
                raise ConflitoDeAgenda(problemas, encaixe=True)
            avisos = problemas

    registro = {
        "id": ident or novo_id("at"),
        "pacienteId": texto(dados.get("pacienteId")),
        "paciente": paciente,
        "tutor": tutor,
        "contato": texto(dados.get("contato"), 60),
        "endereco": texto(dados.get("endereco"), 200),
        "vetId": proposta["vetId"],
        "tipo": tipo,
        "data": proposta["data"],
        "inicio": proposta["inicio"],
        "fim": proposta["fim"],
        "duracao": duracao,
        "status": status,
        "encaixe": encaixe,
        "motivoEncaixe": texto(dados.get("motivoEncaixe"), 300) if encaixe else "",
        "observacoes": texto(dados.get("observacoes"), 2000),
        "reagendadoDe": texto(dados.get("reagendadoDe")),
        "criadoPor": (anterior or {}).get("criadoPor") or texto(quem),
        "criadoEm": (anterior or {}).get("criadoEm") or agora(),
        "atualizadoEm": agora(),
        "atualizadoPor": texto(quem),
        "canceladoEm": (anterior or {}).get("canceladoEm"),
        "canceladoPor": (anterior or {}).get("canceladoPor"),
        "motivoCancelamento": (anterior or {}).get("motivoCancelamento"),
    }

    agenda = [a for a in agenda if a.get("id") != registro["id"]] + [registro]
    _gravar(arm, ARQ_ATENDIMENTOS, agenda,
            ("Atualiza" if anterior else "Agenda") + " atendimento de " + paciente)

    if anterior and (anterior.get("data") != registro["data"]
                     or anterior.get("inicio") != registro["inicio"]):
        registrar(arm, quem, "atendimento.reagendado",
                  "%s: %s %s -> %s %s" % (paciente, _dia_br(anterior.get("data")),
                                          anterior.get("inicio"),
                                          _dia_br(registro["data"]), registro["inicio"]))
    elif anterior:
        registrar(arm, quem, "atendimento.editado",
                  "%s em %s %s" % (paciente, _dia_br(registro["data"]), registro["inicio"]))
    else:
        registrar(arm, quem,
                  "encaixe.criado" if encaixe else "atendimento.criado",
                  "%s com %s em %s %s" % (paciente, registro["vetId"],
                                          _dia_br(registro["data"]), registro["inicio"]))
    return registro, avisos


class ConflitoDeAgenda(Exception):
    """Horario ocupado, fora da disponibilidade, em ferias ou bloqueado."""

    def __init__(self, problemas, encaixe=False):
        self.problemas = problemas
        self.encaixe = encaixe
        super().__init__(" ".join(problemas))


def cancelar_atendimento(arm, ident, motivo, observacao, quem):
    """Nao apaga: muda o status e guarda motivo, momento e autor."""
    agenda = listar_atendimentos(arm)
    alvo = next((a for a in agenda if a.get("id") == ident), None)
    if not alvo:
        raise ValueError("Esse atendimento não existe mais.")
    if alvo.get("status") == "cancelado":
        raise ValueError("Esse atendimento já está cancelado.")

    motivo = texto(motivo) or "Outro"
    alvo["status"] = "cancelado"
    alvo["canceladoEm"] = agora()
    alvo["canceladoPor"] = texto(quem)
    alvo["motivoCancelamento"] = motivo
    alvo["observacaoCancelamento"] = texto(observacao, 500)
    alvo["atualizadoEm"] = agora()

    _gravar(arm, ARQ_ATENDIMENTOS, agenda, "Cancela atendimento de " + str(alvo.get("paciente")))
    registrar(arm, quem, "atendimento.cancelado",
              "%s em %s %s - %s" % (alvo.get("paciente"), _dia_br(alvo.get("data")),
                                    alvo.get("inicio"), motivo))
    return alvo


def mudar_status(arm, ident, status, quem):
    if status not in STATUS:
        raise ValueError("Status desconhecido.")
    if status == "cancelado":
        raise ValueError("Para cancelar, use o cancelamento com motivo.")

    agenda = listar_atendimentos(arm)
    alvo = next((a for a in agenda if a.get("id") == ident), None)
    if not alvo:
        raise ValueError("Esse atendimento não existe mais.")
    alvo["status"] = status
    alvo["atualizadoEm"] = agora()
    alvo["atualizadoPor"] = texto(quem)
    _gravar(arm, ARQ_ATENDIMENTOS, agenda, "Status de " + str(alvo.get("paciente")))
    registrar(arm, quem, "atendimento.status",
              "%s -> %s" % (alvo.get("paciente"), STATUS_ROTULO[status]))
    return alvo


# ================================================================ ESCALA ===
def escala_do_dia(arm, vets, dia, cache=None):
    """Quem trabalha neste dia.

    Sai da disponibilidade menos as ausencias. Se alguem tiver editado a
    escala desse dia a mao, o registro salvo manda - e a resposta diz isso,
    para a tela poder mostrar "escala ajustada".
    """
    cache = cache if cache is not None else {}
    disponibilidade = cache["disp"] if "disp" in cache else listar_disponibilidade(arm)
    ausencias = cache["aus"] if "aus" in cache else listar_ausencias(arm)
    bloqueios = cache["blo"] if "blo" in cache else listar_bloqueios(arm)
    salvas = cache["esc"] if "esc" in cache else _ler(arm, ARQ_ESCALAS)

    iso = dia.isoformat()
    manual = next((e for e in salvas if e.get("data") == iso), None)
    indice = str((dia.weekday() + 1) % 7)

    fora = []
    turnos = {}

    for vet in vets:
        if vet.get("status") == "inativo":
            continue
        vid = vet.get("id")
        ausencia = ausencia_no_dia(ausencias, vid, dia)
        if ausencia:
            fora.append({"vetId": vid, "nome": vet.get("nome"),
                         "tipo": ausencia["tipo"],
                         "ate": ausencia["fim"]})
            continue
        for janela in disponibilidade_do_vet(disponibilidade, vid)["semana"].get(indice, []):
            chave = janela["inicio"] + "-" + janela["fim"]
            turnos.setdefault(chave, []).append({"vetId": vid, "nome": vet.get("nome")})

    derivada = [{"inicio": c.split("-")[0], "fim": c.split("-")[1], "vets": v}
                for c, v in sorted(turnos.items())]

    return {
        "data": iso,
        "diaSemana": DIAS[(dia.weekday() + 1) % 7],
        "turnos": manual["turnos"] if manual else derivada,
        "derivada": manual is None,
        "observacao": (manual or {}).get("observacao", ""),
        "ausentes": fora,
        "bloqueios": [b for b in bloqueios if b.get("data") == iso],
    }


def salvar_escala(arm, dados, quem):
    dia = como_data(dados.get("data"))
    turnos = []
    for t in (dados.get("turnos") or []):
        inicio = em_minutos(t.get("inicio"))
        fim = em_minutos(t.get("fim"))
        if fim <= inicio:
            raise ValueError("O turno %s-%s está invertido."
                             % (t.get("inicio"), t.get("fim")))
        vets = []
        for v in (t.get("vets") or []):
            vid = texto(v.get("vetId") if isinstance(v, dict) else v)
            nome = texto(v.get("nome")) if isinstance(v, dict) else ""
            if vid:
                vets.append({"vetId": vid, "nome": nome})
        turnos.append({"inicio": em_hora(inicio), "fim": em_hora(fim), "vets": vets})
    turnos.sort(key=lambda t: t["inicio"])

    lista = _ler(arm, ARQ_ESCALAS)
    registro = {"id": novo_id("esc"), "data": dia.isoformat(), "turnos": turnos,
                "observacao": texto(dados.get("observacao"), 500),
                "criadoPor": texto(quem), "criadoEm": agora()}
    lista = [e for e in lista if e.get("data") != registro["data"]] + [registro]
    _gravar(arm, ARQ_ESCALAS, lista, "Escala de " + registro["data"])
    registrar(arm, quem, "escala.alterada", "Escala de " + _dia_br(registro["data"]))
    return registro


def remover_escala(arm, dia_iso, quem):
    """Apaga o ajuste manual: o dia volta a seguir a disponibilidade."""
    lista = _ler(arm, ARQ_ESCALAS)
    if not any(e.get("data") == dia_iso for e in lista):
        raise ValueError("Esse dia não tem escala ajustada.")
    _gravar(arm, ARQ_ESCALAS, [e for e in lista if e.get("data") != dia_iso],
            "Remove escala de " + dia_iso)
    registrar(arm, quem, "escala.alterada",
              "Escala de %s voltou a seguir a disponibilidade" % _dia_br(dia_iso))


# ============================================================= DASHBOARD ===
def resumo(arm, vets, hoje=None):
    hoje = hoje or date.today()
    iso = hoje.isoformat()
    agenda = listar_atendimentos(arm)
    ausencias = listar_ausencias(arm)

    do_dia = [a for a in agenda if a.get("data") == iso]
    nomes = {v.get("id"): v.get("nome") for v in vets}

    def enfeitar(a):
        c = dict(a)
        c["vetNome"] = nomes.get(a.get("vetId"), a.get("vetId"))
        return c

    ativos = [a for a in do_dia if a.get("status") != "cancelado"]
    proximos = sorted(
        [a for a in agenda
         if a.get("data") >= iso and a.get("status") in ("agendado", "confirmado")],
        key=lambda a: (a.get("data", ""), a.get("inicio", "")))[:8]

    indisponiveis = []
    for v in vets:
        if v.get("status") == "inativo":
            continue
        fora = ausencia_no_dia(ausencias, v.get("id"), hoje)
        if fora:
            indisponiveis.append({
                "nome": v.get("nome"), "tipo": AUSENCIA_ROTULO[fora["tipo"]],
                "ate": _dia_br(fora["fim"]),
            })

    return {
        "data": iso,
        "cards": {
            "atendimentos": len(ativos),
            "confirmados": len([a for a in ativos if a.get("status") == "confirmado"]),
            "pendentes": len([a for a in ativos if a.get("status") == "agendado"]),
            "encaixes": len([a for a in ativos if a.get("encaixe")]),
            "cancelados": len([a for a in do_dia if a.get("status") == "cancelado"]),
            "realizados": len([a for a in ativos if a.get("status") == "realizado"]),
        },
        "proximos": [enfeitar(a) for a in proximos],
        "indisponiveis": indisponiveis,
    }


# ======================================================= horarios livres ===
def horarios_livres(arm, vets, vet_id, dia_iso, duracao=None):
    """Os horarios em que da para marcar, para a tela oferecer em vez de
    deixar a pessoa tentar na sorte."""
    dia = como_data(dia_iso)
    vet = _vet_ativo(vets, vet_id)
    if not vet:
        return []

    disponibilidade = listar_disponibilidade(arm)
    config = disponibilidade_do_vet(disponibilidade, vet_id)
    duracao = int(duracao or config.get("duracaoPadrao") or DURACAO_PADRAO)

    cache = {"agenda": listar_atendimentos(arm), "disp": disponibilidade,
             "aus": listar_ausencias(arm), "blo": listar_bloqueios(arm)}

    janelas = config["semana"].get(str((dia.weekday() + 1) % 7), [])
    livres = []
    for janela in janelas:
        minuto = em_minutos(janela["inicio"])
        limite = em_minutos(janela["fim"])
        while minuto + duracao <= limite:
            proposta = {"vetId": vet_id, "data": dia.isoformat(),
                        "inicio": em_hora(minuto), "fim": em_hora(minuto + duracao)}
            if not conflitos(arm, vets, proposta, cache=cache):
                livres.append(em_hora(minuto))
            minuto += duracao
    return livres


def listar_auditoria(arm, limite=200):
    return list(reversed(_ler(arm, ARQ_AUDITORIA)))[:limite]


def semana_de(dia):
    """Segunda a domingo da semana deste dia."""
    inicio = dia - timedelta(days=dia.weekday())
    return [inicio + timedelta(days=n) for n in range(7)]
