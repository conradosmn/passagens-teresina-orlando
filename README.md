# Agente de busca diária: hubs → Orlando (jan/2027)

Não existe voo Teresina → Orlando direto. Este agente roda **todo dia
sozinho** (via GitHub Actions) e consulta a Travelpayouts Data API (cache de
preços do Aviasales) para os trechos internacionais **Fortaleza → Orlando
(FOR→MCO)**, **Belém → Orlando (BEL→MCO)** e **Brasília → Orlando
(BSB→MCO)** em janeiro/2027. Guarda o histórico e te manda um **email**
quando o indicador de algum hub cair abaixo do teto que você definir.

A perna **Teresina → hub** ainda não é monitorada (fica pra uma próxima
etapa). Por ora, quando um hub ficar bom, você soma o trecho de Teresina e
confere se os horários casam antes de comprar.

Inclui também um **painel visual** (`docs/index.html`) hospedado de graça no
GitHub Pages — um link fixo que você abre quando quiser, do celular ou do
PC, e vê a estimativa mais barata por hub, uma linha por hub na evolução
diária e as últimas datas monitoradas.

## Por que Travelpayouts e não Amadeus/Duffel

Testamos as três opções nessa ordem, nessa ordem de descarte:

1. **Amadeus for Developers**: o portal self-service parou cadastros novos
   e fecha de vez em 17/07/2026 — sem caminho viável.
2. **Duffel**: cadastro exige "country of incorporation" (empresa
   registrada) e o Brasil não aparece na lista — sem caminho viável para
   quem está aqui sem empresa em outro país.
3. **Travelpayouts** (a que ficou): cadastro de afiliado aberto pra
   qualquer país, sem exigir empresa. A troca é que os dados vêm de um
   **cache de buscas de outros usuários** no Aviasales (não é uma cotação
   ao vivo pro seu grupo), então o valor salvo é uma **estimativa**, não o
   preço exato da família — veja a seção "Limitações honestas" mais abaixo.

## Por que isso resolve o problema do "cookie subindo o preço"

- Não é um navegador, não é scraping de site de venda (Decolar, LATAM, Google
  Flights) — é uma API de dados agregados.
- Cada execução roda numa máquina descartável do GitHub (IP novo, sem
  histórico, sem login). Não existe "sessão sua" para nenhum site inflar.
- Isso é mais seguro contra viés de preço do que abrir o navegador todo dia
  logado na sua conta Google/Decolar para comparar preços manualmente.

## Passo a passo para deixar funcionando

### 1. Criar conta na Travelpayouts (grátis, aberta pra qualquer país)

1. Acesse https://www.travelpayouts.com/ e crie uma conta de afiliado
   (pede nome, email, e um "site" — pode colocar um blog pessoal, perfil
   do Obsidian Publish, ou até um placeholder simples; não precisa de CNPJ
   nem empresa).
2. Depois de logado, vá em **Ferramentas → API** (ou acesse diretamente
   https://www.travelpayouts.com/programs/100/tools/api) para pegar seu
   **token de acesso**.
3. Guarde esse token — é o `TRAVELPAYOUTS_TOKEN` que vai virar secret no
   passo 4 abaixo.

**Ponto de atenção sério:** Teresina→Orlando é uma rota de nicho. Como os
dados vêm de cache de buscas reais de outros usuários, é bem possível que
não haja NENHUM dado pra essa rota específica. Rode o workflow manualmente
uma vez (passo 5) assim que configurar os secrets pra conferir se volta
algo — se vier vazio, me chama que a gente ajusta a estratégia (por
exemplo, testar THE→MIA que tem mais tráfego, ou usar uma rota com escala
já conhecida como referência).

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
| `TRAVELPAYOUTS_TOKEN` | seu token da Travelpayouts (Ferramentas → API) |
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

- `HUBS`: dicionário dos hubs monitorados (código IATA → nome). Já vem com
  Fortaleza, Belém e Brasília; é só adicionar/remover linhas para mudar.
- `MES_BUSCA`: mês de referência (a API devolve o preço mais barato por dia
  desse mês). Está em `2027-01-01` para janeiro/2027.
- `ESTIMATIVA_MULTIPLICADOR`: fator para estimar o total da família (2
  adultos + 2 crianças) a partir do preço de 1 adulto que a API devolve.
  Começa em `3.5` (chute conservador). Depois de comparar com uma cotação
  real no site da companhia, ajuste esse número para calibrar.
- `TETO_PRECO_BRL`: valor de ESTIMATIVA (total da família) abaixo do qual
  você quer ser avisado por email. Rode o workflow manualmente uma vez
  (passo 5) e veja o valor atual no histórico para calibrar.
- `DESTINO`: pode trocar `MCO` (Orlando Intl.) por `MIA` (Miami) — Miami
  tem muito mais tráfego, então a chance de ter dado no cache é bem maior,
  e às vezes é mais barato voar até lá e seguir para Orlando.

## Ver o histórico de preços

Todo dia o robô adiciona os resultados em `docs/data/historico.json` e commita de
volta no repositório. Depois de umas 2-3 semanas rodando, dá pra abrir esse
arquivo (ou pedir pra mim, Claudim, analisar) e ver a tendência do indicador
por data de ida — isso ajuda a decidir a melhor hora de comprar.

## Limitações honestas

- **O valor é uma estimativa, não uma cotação.** Os dados vêm de um cache de
  buscas de outros usuários no Aviasales, tipicamente referentes a 1 adulto.
  O script multiplica por `ESTIMATIVA_MULTIPLICADOR` para chutar o total da
  família — trate como indicador de tendência, não como preço final.
- **Rota de nicho pode não ter dados.** Teresina→Orlando é pouco buscada;
  pode voltar vazio. Se isso acontecer, testar THE→MIA ou uma rota com mais
  tráfego costuma resolver.
- **Não compra a passagem.** Ele só avisa. Quando o indicador ficar bom,
  confirme o preço real (para 2 adultos + 2 crianças, nas datas exatas) no
  site da companhia ou numa agência antes de fechar.
