# Agente de busca diária: hubs → Miami (jan/2027)

Não existe voo Teresina → Miami direto. Este agente roda a cada 2 dias
sozinho (via GitHub Actions) e lê o **Google Flights** (através do SerpApi)
para os trechos **diretos** (sem escala) **Fortaleza → Miami (FOR→MIA)**,
**Belém → Miami (BEL→MIA)**, **Brasília → Miami (BSB→MIA)** e **São Paulo →
Miami (GRU→MIA)** em datas de janeiro/2027, para **2 adultos + 2 crianças**.
Guarda o histórico e te manda um **email** quando o menor preço de algum hub
cair abaixo do teto que você definir.

O preço é o **real do Google Flights** para o grupo exato — não é estimativa.
Só considera voos diretos e traz horários reais.

A perna **Teresina → hub** ainda não é monitorada (fica pra uma próxima
etapa). Por ora, quando um hub ficar bom, você soma o trecho de Teresina e
confere se os horários casam antes de comprar.

Inclui também um **painel visual** (`docs/index.html`) hospedado de graça no
GitHub Pages — um link fixo que você abre quando quiser, do celular ou do
PC, e vê o menor preço por hub, uma linha por hub na evolução diária e as
últimas datas monitoradas.

## Por que SerpApi (Google Flights) e não Amadeus/Duffel/Travelpayouts

Testamos quatro opções, nesta ordem de descarte:

1. **Amadeus for Developers**: portal self-service parou cadastros novos e
   fecha de vez em 17/07/2026 — sem caminho viável.
2. **Duffel**: cadastro exige "country of incorporation" (empresa
   registrada) e o Brasil não aparece na lista — sem caminho viável para
   quem está aqui sem empresa em outro país.
3. **Travelpayouts**: cadastro aberto, mas o endpoint de preços não retornou
   dado nenhum — nem para rota popular (GRU→MCO). O cache não cobre o que a
   gente precisa.
4. **SerpApi** (a que ficou): lê o próprio **Google Flights**, então cobre
   suas rotas de verdade, com voo casado e horários reais, e devolve o preço
   para o grupo exato (2 adultos + 2 crianças). Plano gratuito de 250
   buscas/mês — folgado para o uso deste agente (~3-9 buscas/dia).

## Por que isso resolve o problema do "cookie subindo o preço"

- Não é o seu navegador, não guarda cookies, não faz login em site de venda.
- Cada execução roda numa máquina descartável do GitHub (IP novo, sem
  histórico, sem login), e a leitura do Google Flights sai pelo SerpApi, não
  pela sua sessão. Não existe "sessão sua" para nenhum site inflar.

## Passo a passo para deixar funcionando

### 1. Criar conta no SerpApi (grátis, 250 buscas/mês)

1. Acesse https://serpapi.com/users/sign_up e crie a conta (pode usar login
   com Google). Não precisa cadastrar cartão para o plano grátis; se pedir
   verificação por telefone, é só antifraude.
2. Depois de logado, pegue sua chave em
   https://serpapi.com/manage-api-key — é uma sequência longa de
   letras/números.
3. Guarde essa chave — é o `SERPAPI_KEY` que vira secret no passo 4 abaixo.

**Sobre a cota:** cada busca é 1 rota + 1 data. Com 4 hubs × 3 datas de ida
(padrão do script) são 12 buscas por execução; rodando dia sim/dia não
(padrão do workflow) dá ~180/mês — dentro das 250 grátis com folga.

### 2. Criar um "app password" do Gmail (ou outro provedor SMTP)
1. Se usar Gmail: ative a verificação em duas etapas na conta e gere uma
   "senha de app" em https://myaccount.google.com/apppasswords.
2. Guarde essa senha — é diferente da sua senha normal do Gmail.
3. Pode usar outro provedor (Outlook, etc.) — só ajustar o host/porta SMTP
   no `buscar_passagens.py` se não for Gmail.

### 3. Subir este projeto para um repositório no GitHub
```bash
cd passagens-teresina-orlando
git init
git add .
git commit -m "Primeiro commit: agente de busca de passagens"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/passagens-teresina-orlando.git
git push -u origin main
```
Pode deixar o repositório **privado** (recomendado, já que ele guarda seu
histórico de buscas).

### 4. Configurar os "Secrets" no GitHub
No repositório: **Settings → Secrets and variables → Actions → New repository secret**.
Criar estes 4 secrets:

| Nome | Valor |
|---|---|
| `SERPAPI_KEY` | sua chave do SerpApi (manage-api-key) |
| `EMAIL_USER` | seu email (ex: seuemail@gmail.com) |
| `EMAIL_PASS` | a senha de app gerada no passo 2 |
| `EMAIL_TO` | email para onde quer receber o alerta (pode ser o mesmo) |

### 5. Ativar o workflow
O arquivo `.github/workflows/busca_diaria.yml` já está configurado para
rodar **todo dia às 09:00 (horário de Brasília)**. Assim que você fizer o
push, ele já fica agendado — não precisa fazer mais nada.

Se quiser testar na hora sem esperar o cron: vá na aba **Actions** do
repositório → selecione o workflow → **Run workflow**.

### 6. Ativar o painel visual (GitHub Pages)

O painel (`docs/index.html`) é um placar estilo aeroporto que lê
`docs/data/historico.json` e mostra a menor tarifa encontrada, a evolução do
preço dia a dia e as últimas combinações de data testadas.

1. No repositório: **Settings → Pages**.
2. Em "Build and deployment" → Source: **Deploy from a branch**.
3. Branch: **main**, pasta: **/docs** → Save.
4. Em 1-2 minutos o GitHub te dá um link tipo
   `https://SEU_USUARIO.github.io/passagens-teresina-orlando/` — salva esse
   link nos favoritos do celular. Toda vez que o robô rodar e atualizar o
   histórico, o painel reflete automaticamente (só dar refresh na página).

Se o repositório for privado, o GitHub Pages também funciona (fica com o
link "escondido", mas não é 100% privado — quem tiver o link acessa; se isso
for um problema, me avisa que a gente troca a abordagem para algo com senha).

## Ajustando parâmetros

Tudo que você provavelmente vai querer mexer está no topo do
`buscar_passagens.py`, na seção `CONFIGURAÇÃO`:

- `HUBS`: dicionário dos hubs monitorados (código IATA → nome). Vem com
  Fortaleza, Belém, Brasília e São Paulo (GRU).
- `MONITORAR_DOMESTICO`: liga/desliga a busca da perna Teresina → hub. Com
  ela ligada, o painel mostra o total porta a porta (doméstico + internacional).
- `DATA_DOMESTICA_IDA` / `DATA_DOMESTICA_VOLTA`: datas do voo Teresina → hub
  (a perna doméstica é buscada 1 vez por hub, não por data internacional,
  para economizar cota).
- `DATAS_IDA`: lista de datas de ida internacionais testadas. Cada data =
  1 busca por hub.
- `DURACAO_VIAGEM_DIAS`: quantos dias de viagem (define a data de volta).
- `ADULTOS` / `CRIANCAS`: composição do grupo (já em 2 e 2).
- `TETO_PRECO_BRL`: preço total do grupo (porta a porta) abaixo do qual você
  quer o alerta por email. Está em R$ 20.000; ajuste conforme os valores reais.
- `DESTINO`: `MIA` (Miami) — só voo direto. Orlando (`MCO`) não tem voo
  direto saindo do Brasil, por isso não é mais monitorado.

**Consumo da cota (250 buscas/mês grátis) — configuração atual:**
- 4 hubs (FOR/BEL/BSB/GRU) × 3 datas = 12 buscas por execução, sempre com
  filtro de voo direto (`stops=1` no SerpApi)
- Doméstico desligado (`MONITORAR_DOMESTICO = False`) — os preços THE→hub
  variam pouco; use os valores de referência já coletados no histórico
- Agendamento: **dia sim/dia não** (cron `0 12 */2 * *`) → ~180 buscas/mês,
  dentro das 250 grátis com folga
- Se religar o doméstico ou voltar pra diário, refaça a conta pra não estourar

## Ver o histórico de preços

Todo dia o robô adiciona os resultados em `docs/data/historico.json` e commita de
volta no repositório. Depois de umas 2-3 semanas rodando, dá pra abrir esse
arquivo (ou pedir pra mim, Claudim, analisar) e ver a tendência de preço por
hub e por data — isso ajuda a decidir a melhor hora de comprar.

## Limitações honestas

- **Cota gratuita.** São 250 buscas/mês no plano free do SerpApi. O padrão
  (4 hubs × 3 datas = 12 buscas por execução, dia sim/dia não) fica dentro
  do grátis com folga; se aumentar hubs/datas ou a frequência, refaça a conta.
- **Dois trechos separados.** O total soma Teresina → hub (doméstico) + hub →
  Miami (sempre voo direto), comprados separadamente. Confira se o horário de
  chegada do doméstico casa com a saída do internacional antes de comprar.
- **Não compra a passagem.** Ele só avisa. O preço vem do Google Flights;
  confirme no site da companhia (datas e passageiros exatos) antes de fechar.
