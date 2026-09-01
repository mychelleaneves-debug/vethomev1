# Operação da clínica

Agenda, disponibilidade, escalas, bloqueios, férias e cancelamentos — dentro do
mesmo painel da equipe, no menu **OPERAÇÃO**.

---

## Antes de tudo: o repositório privado

Um agendamento carrega **nome do pet, nome do tutor, telefone, endereço e
observações clínicas**. São dados dos seus clientes. O repositório do site é
público (tem que ser, senão o GitHub Pages não publica), então a operação
grava em outro lugar.

### O que você precisa fazer, uma vez só

**1. Criar o repositório privado**

1. <https://github.com/new>
2. **Repository name:** `vethome-operacao`
3. Marque **Private** — esta é a parte que importa
4. Marque **Add a README file** (sem isso o branch `main` não existe e a
   primeira gravação falha)
5. **Create repository**

**2. Dar acesso ao token**

1. <https://github.com/settings/tokens?type=beta> → clique em `vethometoken`
2. Em **Repository access**, com `Only select repositories` marcado, adicione
   `vethome-operacao` à lista (o `vethomev1` continua lá)
3. **Update** — o código do token não muda, não precisa mexer no Render

**3. Avisar o Render onde é**

Render → o serviço → **Environment** → **+ Add variable**:

| KEY | VALUE |
|---|---|
| `GITHUB_REPO_DADOS` | `mychelleaneves-debug/vethome-operacao` |

→ **Save, rebuild, and deploy**.

Enquanto isso não estiver feito, o menu OPERAÇÃO aparece esmaecido e, ao
clicar, explica o que falta. O resto do painel funciona normalmente.

**No seu computador não precisa de nada disso.** O painel local grava numa
pasta `dados/` dentro do projeto, que fica fora do Git.

---

## Como as peças se encaixam

```
                    VETERINÁRIO
                (o mesmo do site, sem cadastro duplicado)
                         │
          ┌──────────────┼──────────────┐
          ↓              ↓              ↓
   DISPONIBILIDADE   FÉRIAS/FOLGAS   BLOQUEIOS
   (toda semana)     (dias inteiros)  (um horário)
          │              │              │
          └──────────────┼──────────────┘
                         ↓
                      ESCALA
              (sai sozinha das três acima)
                         │
                         ↓
                      AGENDA
                         │
              ┌──────────┼──────────┐
              ↓          ↓          ↓
           Normal    Encaixe    Cancelado
```

A disponibilidade, as ausências e os bloqueios dizem **quando** cada
veterinário pode atender. A agenda confere as três antes de aceitar um
horário. A escala não é um cadastro à parte: ela é calculada a partir delas —
e só vira registro próprio quando você edita um dia à mão.

---

## As telas

### Painel
Contadores de hoje (atendimentos, confirmados, a confirmar, encaixes,
realizados, cancelados), próximos atendimentos e quem está fora hoje.

### Agenda
Dia, semana e mês. No celular abre em Dia — a semana inteira não cabe.

- Filtros por veterinário, tipo, status e data
- Encaixe aparece com borda tracejada
- Dois atendimentos no mesmo horário dividem a coluna, um não cobre o outro
- Clicar num atendimento abre o detalhe, com Confirmar / Em atendimento /
  Realizado / Faltou, Editar e Cancelar

Ao escolher veterinário e data, o formulário mostra **os horários livres**
daquele dia, já descontando o que está ocupado, bloqueado ou fora do
expediente. É mais rápido do que tentar na sorte.

### Disponibilidade
Os horários que se repetem toda semana, por veterinário. Vários períodos no
mesmo dia (manhã e tarde), **Copiar para…** joga um dia nos outros, e
**Copiar segunda para a semana toda** resolve o caso comum.

A **duração padrão** define os horários que a agenda oferece: 40 minutos gera
08:00, 08:40, 09:20…

### Escalas
Quem trabalha em cada dia da semana, por turno. Vem pronta da
disponibilidade, descontando férias e folgas — o selo diz **Automática**.
Editar um dia cria um ajuste só para ele (selo **Ajustada**), e
**Desfazer ajuste** devolve o dia ao cálculo automático.

### Bloqueios
Buracos pontuais: reunião, manutenção, treinamento, evento, almoço
excepcional. Pode ser de um veterinário ou **da clínica inteira**.

### Férias e folgas
Períodos de dias inteiros. Durante eles a agenda recusa novos agendamentos
para aquela pessoa, e ela some da escala.

### Cancelamentos
Todos os cancelados, com motivo, quem cancelou e quando. **Nada é apagado** —
o atendimento continua guardado com status `cancelado`. Dá para reagendar a
partir dali, e o novo atendimento guarda de qual ele veio.

### Pacientes
Cadastro opcional de pet + tutor, só para preencher a agenda mais rápido. Dá
para agendar digitando o nome direto, sem cadastrar antes.

### Histórico
As últimas ações: quem criou, editou, cancelou, reagendou, quem mexeu em
disponibilidade, bloqueio, férias e escala.

---

## Conflitos

O servidor recusa e **explica** quando:

| Situação | O que aparece |
|---|---|
| Já tem atendimento nesse horário | "Este horário já possui atendimento: Thor às 09:00, Consulta." |
| Fora do expediente | "Fora da disponibilidade de Dra. X nesse dia (08:00-12:00, 14:00-18:00)." |
| Dia em que não atende | "Dra. X não atende sábado." |
| Férias ou folga | "Dra. X está de férias de 10/09/2026 até 20/09/2026." |
| Bloqueio | "Há um bloqueio para a clínica: Reunião, das 17:00 às 18:00." |

A validação é no **servidor**, não só na tela. Mandar direto pela API não
passa por cima dela.

### Encaixe

Marque **Marcar como encaixe** no formulário. Aí o conflito vira aviso:

> Este horário tem conflito.
> • Este horário já possui atendimento: Thor às 09:00, Consulta.
>
> [Voltar] [Confirmar encaixe]

Só grava depois do clique em **Confirmar encaixe**. O atendimento que já
existia não é tocado nem movido. Fica registrado quem criou, o motivo do
encaixe, e o histórico marca como `encaixe.criado`.

---

## Como testar cada coisa

Com o painel aberto em <http://localhost:8791/admin>:

| O quê | Como |
|---|---|
| Disponibilidade | Disponibilidade → escolha alguém → + horário → Salvar |
| Agendamento | Agenda → + Novo atendimento → escolha vet e data → clique num horário livre → Salvar |
| Conflito | Repita o mesmo horário → tem que recusar explicando |
| Encaixe | Repita marcando "encaixe" → confirmar → os dois aparecem lado a lado |
| Bloqueio | Bloqueios → + Novo → volte à agenda: o horário some dos livres |
| Férias | Férias e folgas → + Novo → tente agendar naquele dia → recusa |
| Cancelamento | Clique no atendimento → Cancelar → escolha o motivo |
| Reagendamento | Cancelamentos → Reagendar → escolha outro horário |
| Escala | Escalas → confira que quem está de férias sumiu → Editar → Salvar |
| Celular | Abra o painel no celular: menu vira ☰ e a agenda abre em Dia |

Ou tudo de uma vez, sem clicar em nada:

```bash
python tools/teste_operacao.py
```

São 76 verificações, do login ao encaixe confirmado. Ele guarda a pasta
`dados/` antes de começar e devolve como estava — pode rodar mesmo com agenda
de verdade lá dentro.

---

## Limitações, ditas na cara

**Não há papéis de verdade.** O painel tem uma senha só, compartilhada. Ao
entrar, cada pessoa digita o próprio nome, e é isso que fica no histórico
("criado por Mychelle", "cancelado por Ana"). Mas todo mundo que tem a senha
enxerga e faz tudo. Os papéis administrador / gerente / veterinário do pedido
original não existem — criar isso significa criar um sistema de usuários, que
é outro projeto.

**Duas pessoas salvando no mesmo segundo.** Cada gravação é um commit no
GitHub. Se duas pessoas salvarem exatamente ao mesmo tempo, uma recebe
"Alguém salvou antes de você. Recarregue a página e tente de novo." Nada se
perde, mas é preciso refazer. Para duas ou três pessoas usando, isso quase
nunca acontece.

**Sem lembretes automáticos.** O painel não manda WhatsApp nem e-mail para o
tutor. Confirmação continua sendo feita à mão.

**Sem prontuário.** As observações do atendimento são um campo de texto, não
um histórico clínico do animal.

**O que fica guardado:** os últimos 3.000 registros do histórico. Os mais
antigos saem para o arquivo não crescer sem fim.
