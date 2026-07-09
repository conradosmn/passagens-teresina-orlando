# MEMORIA.md — Contexto do projeto para Claude (Code)

> Este arquivo resume o histórico e as decisões do projeto, construído em
> conversa com Claude (chat) em julho/2026. Leia antes de mexer em qualquer
> coisa. Dono do projeto: Conrado (Teresina-PI).

## O que este projeto é

Agente automático de monitoramento de preço de passagens aéreas para uma
viagem familiar **Teresina → Miami**, **2 adultos + 2 crianças**, por
**~10 dias na SEGUNDA SEMANA de janeiro/2027** (idas testadas: 08, 10 e
12/01; voltas 10 dias depois).

> **Atualizado em 09/07/2026**: o destino internacional mudou de Orlando
> (MCO) para **Miami (MIA)**, e agora só interessam **voos diretos** (sem
> escala) no trecho internacional — ver decisão #9 e §"Como funciona a busca".

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

1. Para cada origem em `HUBS` (FOR, BEL, BSB, GRU) × cada data em
   `DATAS_IDA` (3 datas): busca ida-e-volta **hub → MIA (DESTINO)** no Google
   Flights (SerpApi), econômica, 2 adultos + 2 crianças, moeda BRL, **só voo
   direto** (`apenas_direto=True` em `buscar_voo` → `stops=1` no SerpApi).
   **12 buscas por execução** (4 hubs × 3 datas).
2. **THE (Teresina) foi removido de `HUBS`**: não existe voo internacional
   direto saindo de Teresina, então com o filtro de voo direto a busca nunca
   dava resultado — mantê-lo só desperdiçava cota. `ORIGEM_DOMESTICA = "THE"`
   continua existindo (é de onde sai a perna doméstica Teresina → hub).
3. Aos demais hubs, soma-se ao preço internacional um **valor doméstico
   de REFERÊNCIA fixo** (THE→hub ida-e-volta), definido em
   `DOMESTICO_REFERENCIA` no script — a busca doméstica ao vivo está
   DESLIGADA (`MONITORAR_DOMESTICO = False`) para economizar cota.
   Valores de referência coletados em busca real de 07/07/2026 (quando o
   destino ainda era MCO — a perna doméstica Teresina→hub não muda com o
   destino internacional, então seguem válidos):
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
   diferença). Foi assim que decidimos monitorar hub → destino em vez de
   deixar o Google montar a conexão sozinho a partir de Teresina.
6. **GRU mantido como hub** (foi o mais barato no teste).
7. **Cota**: com 4 hubs (sem THE) × 3 datas = 12 buscas/execução, ~15
   execuções/mês ≈ 180 → cabe nas 250 grátis com folga. NÃO voltar para
   execução diária nem religar o doméstico sem refazer a conta.
8. **Preços observados caem ao longo de janeiro** (15/01 mais barato que
   05/01 em todos os hubs) — fim das férias escolares. A segunda semana pega
   o meio da curva.
9. **Destino trocado de Orlando (MCO) para Miami (MIA) + só voo direto**
   (decisão de 09/07/2026, a pedido do Conrado: ele não quer voo com escala).
   THE saiu de `HUBS` porque o filtro de voo direto (`stops=1`) nunca dava
   resultado a partir de Teresina — sem sentido gastar cota com isso. Não é
   fallback (MCO se não tiver MIA, ou vice-versa): é substituição definitiva,
   só MIA é buscado agora. Histórico antigo (`historico.json`) tem registros
   de MCO anteriores a essa data — misturados no mesmo gráfico/tabela com os
   novos registros de MIA; se isso confundir a leitura do painel, considerar
   filtrar por data ou limpar o histórico antigo (ainda não decidido).

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
  real da ida internacional (companhia, voo, horários; agora sempre voo
  direto, sem conexões) + média por passageiro. Alimentada pelo campo
  `detalhes_ida`, capturado da MESMA resposta do SerpApi (não gasta busca
  extra). A gravação é idempotente por dia (rodar 2x no mesmo dia substitui,
  não duplica).

## Fluxo de trabalho com git (duas máquinas!)

O projeto é editado do laptop E do desktop, e o **robô também commita**
(histórico) a cada execução. Regra de ouro: **`git pull` antes de editar e
antes de push**. Push rejeitado = alguém (provavelmente o robô) commitou;
resolver com `git pull origin main --no-rebase` e concluir o merge.

## Pendências / próximos passos possíveis

- [ ] Confirmar que o push da mudança de destino (MCO → MIA, só voo direto,
      hub THE removido) subiu certinho.
- [ ] Rodar o workflow manualmente 1x pra ver se os hubs têm voo direto pra
      Miami nas datas monitoradas (se algum hub não tiver, a busca daquele
      hub/data simplesmente não retorna nada — sem erro, sem alerta).
- [ ] Recalibrar `TETO_PRECO_BRL` (hoje R$ 20.000) com base nos novos preços
      MIA + voo direto — pode ser bem diferente do que era com MCO.
- [ ] A cada 1-2 meses, atualizar `DOMESTICO_REFERENCIA` (religar
      `MONITORAR_DOMESTICO = True` por UMA rodada, copiar os valores, desligar).
- [ ] Decidir o que fazer com o histórico antigo de MCO em
      `docs/data/historico.json` (manter misturado, filtrar por data no
      painel, ou limpar) — ver decisão #9.
- [ ] Ideia futura: validar horários de conexão entre trechos separados
      (hoje o robô soma preços mas não confere se os horários casam — o
      usuário confere manualmente antes de comprar).

## Estilo de trabalho com o Conrado

Comunicação em PT-BR, tom casual (ele chama Claude de "Claudim"). Ele é
engenheiro (obras públicas/orçamentos, TCE-PI), confortável com planilhas e
lógica, mas o fluxo git/terminal é novo — explicar comandos passo a passo,
um de cada vez, e antecipar erros comuns (Vim: `Esc` + `:wq` + `Enter`).
Ser honesto sobre limitações e custos antes de implementar.
