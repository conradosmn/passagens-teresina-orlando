# MEMORIA.md — Contexto do projeto para Claude (Code)

> Este arquivo resume o histórico e as decisões do projeto, construído em
> conversa com Claude (chat) em julho/2026. Leia antes de mexer em qualquer
> coisa. Dono do projeto: Conrado (Teresina-PI).

## O que este projeto é

Agente automático de monitoramento de preço de passagens aéreas para uma
viagem familiar **Teresina → Orlando**, **2 adultos + 2 crianças**, por
**~10 dias na SEGUNDA SEMANA de janeiro/2027** (idas testadas: 08, 10 e
12/01; voltas 10 dias depois).

Roda sozinho via **GitHub Actions** (dia sim/dia não), consulta o **Google
Flights via SerpApi**, salva histórico em `docs/data/historico.json`
(commitado de volta pelo próprio workflow), publica um **painel visual** no
GitHub Pages e envia **email de alerta** quando o total porta a porta cai
abaixo do teto.

- Painel: https://conradosmn.github.io/passagens-teresina-orlando/
- Repo: https://github.com/conradosmn/passagens-teresina-orlando (público —
  necessário para o Pages funcionar no plano grátis)

## Arquitetura (arquivos)

- `buscar_passagens.py` — script principal. Toda a configuração editável
  fica no topo (seção CONFIGURAÇÃO).
- `.github/workflows/busca_diaria.yml` — agendamento (cron `0 12 */2 * *` =
  dia sim/dia não, 9h Brasília) + commit automático do histórico.
- `docs/index.html` — painel (placar estilo aeroporto, dark, Chart.js).
  Lê `docs/data/historico.json` via fetch.
- `docs/data/historico.json` — histórico acumulado de preços.

## Como funciona a busca (lógica atual)

1. Para cada origem em `HUBS` (THE, FOR, BEL, BSB, GRU) × cada data em
   `DATAS_IDA` (3 datas): busca ida-e-volta no Google Flights (SerpApi),
   econômica, 2 adultos + 2 crianças, moeda BRL. **15 buscas por execução.**
2. **THE = "Teresina direto"**: o Google monta a conexão sozinho num bilhete
   único. Serve de comparação contra a estratégia de trechos separados.
3. Para os demais hubs, soma-se ao preço internacional um **valor doméstico
   de REFERÊNCIA fixo** (THE→hub ida-e-volta), definido em
   `DOMESTICO_REFERENCIA` no script — a busca doméstica ao vivo está
   DESLIGADA (`MONITORAR_DOMESTICO = False`) para economizar cota.
   Valores de referência coletados em busca real de 07/07/2026:
   FOR 7.878 / BEL 8.496 / BSB 6.670 / GRU 8.125 (R$, grupo todo, ida-volta).
4. O menor total (porta a porta) do dia é comparado ao `TETO_PRECO_BRL`
   (atualmente **R$ 20.000**); abaixo disso, dispara email.

## Decisões tomadas e POR QUÊ (não refazer o caminho errado)

1. **Amadeus** — descartada: portal self-service parou cadastros e fecha em
   17/07/2026.
2. **Duffel** — descartada: cadastro exige "country of incorporation" e
   Brasil não está na lista.
3. **Travelpayouts** — descartada: endpoint month-matrix não retornou dado
   NENHUM, nem para GRU→MCO (rota popular). Testado de verdade.
4. **SerpApi (Google Flights)** — ESCOLHIDA. Funciona, preço real do grupo,
   plano grátis de 250 buscas/mês. Conta do Conrado: Free Plan.
5. **Trechos separados vencem o bilhete único**: no teste real (07/07/2026),
   THE direto deu R$ 34.029 vs. THE→GRU + GRU→MCO = R$ 23.143 (R$ 11 mil de
   diferença). Por isso monitoramos os dois: THE direto fica como comparação.
6. **GRU mantido como hub** (foi o mais barato no teste); THE mantido com
   flag visual de caro no painel.
7. **Cota**: 15 buscas × ~15 execuções/mês ≈ 225 → cabe nas 250 grátis.
   NÃO voltar para execução diária nem religar o doméstico sem refazer a conta.
8. **Preços observados caem ao longo de janeiro** (15/01 mais barato que
   05/01 em todos os hubs) — fim das férias escolares. A segunda semana pega
   o meio da curva.

## Secrets configurados no GitHub (Settings → Secrets → Actions)

- `SERPAPI_KEY` — chave do SerpApi (https://serpapi.com/manage-api-key)
- `EMAIL_USER` / `EMAIL_PASS` / `EMAIL_TO` — Gmail + senha de app (16 letras)
- (`TRAVELPAYOUTS_TOKEN` é legado; pode ser deletado se ainda existir)

## Painel — pontos de atenção

- `const TETO_PRECO` no `docs/index.html` deve SEMPRE bater com
  `TETO_PRECO_BRL` do script (hoje: 20000).
- Selos de preço na tabela: "melhor" (verde) para o menor da mesma data de
  ida; amarelo até +30%; vermelho (+30% ou mais) = flag de caro.
- Cores por hub no gráfico: FOR laranja, BEL teal, BSB roxo, GRU azul.
- Campos do histórico: `data_busca, hub, hub_nome, data_ida, data_volta,
  preco_internacional_brl, preco_domestico_brl (pode ser null),
  preco_total_brl, preco_medio_passageiro_brl (total/4), detalhes_ida
  (itinerário da ida internacional: segmentos + layovers + duração; pode ser
  null em registros antigos), fonte`.
- **Cascata da viagem** no painel: mostra a melhor combinação do dia detalhada
  — trecho doméstico como estimativa de referência (sem voos) + itinerário
  real da ida internacional (companhia, voo, horários, conexões) + média por
  passageiro. Alimentada pelo campo `detalhes_ida`, capturado da MESMA resposta
  do SerpApi (não gasta busca extra). A gravação é idempotente por dia (rodar
  2x no mesmo dia substitui, não duplica).

## Fluxo de trabalho com git (duas máquinas!)

O projeto é editado do laptop E do desktop, e o **robô também commita**
(histórico) a cada execução. Regra de ouro: **`git pull` antes de editar e
antes de push**. Push rejeitado = alguém (provavelmente o robô) commitou;
resolver com `git pull origin main --no-rebase` e concluir o merge.

## Pendências / próximos passos possíveis

- [ ] Confirmar que o push das últimas mudanças (datas 08/10/12-jan +
      economia de cota) subiu a partir do desktop.
- [ ] Rodar o workflow manualmente 1x para popular o histórico com os preços
      do período correto (segunda semana de janeiro).
- [ ] Calibrar `TETO_PRECO_BRL` conforme a tendência real (hoje R$ 20.000;
      o melhor total visto foi R$ 23.143).
- [ ] A cada 1-2 meses, atualizar `DOMESTICO_REFERENCIA` (religar
      `MONITORAR_DOMESTICO = True` por UMA rodada, copiar os valores, desligar).
- [ ] Ideia futura: validar horários de conexão entre trechos separados
      (hoje o robô soma preços mas não confere se os horários casam — o
      usuário confere manualmente antes de comprar).

## Estilo de trabalho com o Conrado

Comunicação em PT-BR, tom casual (ele chama Claude de "Claudim"). Ele é
engenheiro (obras públicas/orçamentos, TCE-PI), confortável com planilhas e
lógica, mas o fluxo git/terminal é novo — explicar comandos passo a passo,
um de cada vez, e antecipar erros comuns (Vim: `Esc` + `:wq` + `Enter`).
Ser honesto sobre limitações e custos antes de implementar.
