# Painel da equipe no Render (de graça)

O painel roda em dois lugares, com o mesmo código:

| | No seu computador | No Render |
|---|---|---|
| Como abre | atalho **PAINEL DA EQUIPE - VetHome** | um endereço na internet |
| Quem consegue entrar | só quem está nesta máquina | quem tiver o endereço e a senha |
| Onde salva | nos arquivos da pasta `site/` | direto no GitHub |
| O site atualiza | quando você publicar | sozinho, em ~1 minuto |

Nada muda na landing page. O painel só mexe na lista de veterinários.

---

## Por que salva no GitHub e não no servidor

O plano gratuito do Render apaga o disco a cada reinício — e ele reinicia
sozinho todo dia. Se o painel gravasse em arquivo lá, todo veterinário
cadastrado sumiria sem aviso.

Por isso ele grava direto no repositório, no mesmo branch (`gh-pages`) que
publica o site. Consequência boa: salvar no painel **já atualiza o site**.
Não existe passo de "publicar" separado.

---

## O que você precisa fazer (3 passos)

### 1. Gerar o token do GitHub

O token é a chave que deixa o painel escrever no repositório. Sem ele, o
painel abre mas não salva nada.

1. Entre em <https://github.com/settings/personal-access-tokens/new>
2. **Token name:** `painel-vethome`
3. **Expiration:** escolha `No expiration` (ou 1 ano — mas aí precisará
   refazer isso quando vencer)
4. **Repository access:** marque **Only select repositories** e escolha
   `mychelleaneves-debug/vethomev1`
5. Em **Permissions → Repository permissions**, procure **Contents** e mude
   de `No access` para **Read and write**. É a única permissão necessária.
6. Clique em **Generate token**
7. Copie o código que aparece (começa com `github_pat_`). **Ele só aparece
   uma vez** — se fechar a página, é só gerar outro.

### 2. Criar o serviço no Render

1. Em <https://dashboard.render.com>, clique em **New +** → **Web Service**
2. Conecte a conta do GitHub e escolha o repositório `vethomev1`
3. O Render vai ler o arquivo `render.yaml` e preencher quase tudo sozinho.
   Confira que ficou assim:
   - **Branch:** `main`
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python tools/cms.py`
   - **Instance Type:** `Free`

### 3. Colar as duas senhas

Ainda na tela de criação, em **Environment Variables**, o Render vai pedir
os dois valores que de propósito não estão no código:

| Nome | O que colar |
|---|---|
| `GITHUB_TOKEN` | o código do passo 1 |
| `CMS_SENHA` | a senha que você e sua sócia vão usar para entrar no painel |

Escolha uma senha de pelo menos 10 caracteres. Ela não fica escrita em lugar
nenhum do código — o servidor guarda só o embaralhado dela.

Clique em **Create Web Service** e espere uns 2 minutos.

---

## Usando

O Render te dá um endereço tipo `https://vethome-painel.onrender.com`.
O painel fica em **`/admin`** — mas se digitar só o endereço, ele leva para
lá sozinho.

Mande esse endereço e a senha para sua sócia. Só isso.

### Duas coisas do plano gratuito, para não assustar

**A primeira abertura do dia demora.** O Render desliga o serviço depois de
15 minutos parado e liga de novo quando alguém acessa. A tela fica em branco
por uns 50 segundos. Da segunda vez em diante é instantâneo.

**O site demora ~1 minuto para mostrar a mudança.** Ao salvar, o painel
grava no GitHub; o GitHub Pages republica logo depois. Se atualizar a página
do site e não vir a mudança, espere um pouco e atualize de novo.

---

## Se der errado

O painel avisa em português o que aconteceu:

| Mensagem | O que fazer |
|---|---|
| "O token do GitHub foi recusado. Ele pode ter expirado." | Gerar um token novo (passo 1) e trocar o valor de `GITHUB_TOKEN` no Render, em **Environment** |
| "O token não tem permissão de escrita neste repositório." | O token foi criado sem **Contents: Read and write**, ou sem marcar o repositório certo. Gerar de novo. |
| "Alguém salvou antes de você." | Você e sua sócia salvaram ao mesmo tempo. Recarregar a página e refazer. |
| "Não consegui falar com o GitHub" | Instabilidade momentânea. Tentar de novo em um minuto. |

Para trocar a senha do painel depois: Render → o serviço → **Environment** →
editar `CMS_SENHA` → **Save**. O serviço reinicia sozinho.

---

## O painel no seu computador continua funcionando

O atalho na área de trabalho não muda em nada. Lá ele grava nos arquivos da
pasta `site/`, como sempre, sem depender de internet nem do token.
