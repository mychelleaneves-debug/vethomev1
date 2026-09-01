# -*- coding: utf-8 -*-
"""Acrescenta ao veterinarios.json os campos que o CMS precisa.

Roda uma vez so. Nao inventa conteudo: os campos novos que dependem de
informacao que so a VetHome tem (cidade, areas de atuacao) entram vazios,
para serem preenchidos no painel. Os que dao para deduzir com seguranca
(cargo pelo Dr./Dra., slug pelo nome, ordem pela posicao atual) ja vem
preenchidos.
"""
import json, re, unicodedata, shutil, os, sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARQ = os.path.join(BASE, "site", "data", "veterinarios.json")


def slugificar(nome):
    s = unicodedata.normalize("NFKD", nome)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def main():
    with open(ARQ, encoding="utf-8") as f:
        vets = json.load(f)

    if vets and "status" in vets[0]:
        print("ja migrado, nada a fazer")
        return

    shutil.copy(ARQ, ARQ + ".antes-do-cms")
    print("backup: veterinarios.json.antes-do-cms")

    usados = set()
    novos = []
    for i, v in enumerate(vets, start=1):
        nome = v.get("nome", "").strip()

        slug = slugificar(nome)
        base = slug
        n = 2
        while slug in usados:
            slug = base + "-" + str(n)
            n += 1
        usados.add(slug)

        # "Dr." -> masculino, "Dra." -> feminino; qualquer outra coisa fica neutro
        if re.match(r"^dra\.?\s", nome, re.I):
            cargo = "Médica-Veterinária"
        elif re.match(r"^dr\.?\s", nome, re.I):
            cargo = "Médico-Veterinário"
        else:
            cargo = "Médico(a)-Veterinário(a)"

        novos.append({
            "id": slug,
            "nome": nome,
            "cargo": cargo,
            "especialidade": v.get("especialidade", ""),
            "crmv": v.get("crmv", ""),
            "cidade": "",                 # so a VetHome sabe: preencher no painel
            "foto": v.get("foto", ""),
            "descricao": v.get("descricao", ""),
            "areas": [],                  # idem
            "status": "ativo",
            "ordem": i,
            "slug": slug,
        })

    with open(ARQ, "w", encoding="utf-8") as f:
        json.dump(novos, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("migrados: %d veterinarios" % len(novos))
    print("exemplo:", json.dumps(novos[0], ensure_ascii=False)[:150])


if __name__ == "__main__":
    main()
