#!/usr/bin/env python3
"""
Agente de busca diária de passagens rumo a Miami (jan/2027)
2 adultos + 2 crianças -- preço REAL do grupo, via Google Flights (SerpApi).

Só interessam voos DIRETOS (sem escalas). Não existe voo Teresina -> Miami
direto, então o agente monitora o trecho internacional direto a partir dos
hubs que voam sem escala pra Miami (Fortaleza, Belém, Brasília, São Paulo).
A perna Teresina -> hub é doméstica e você casa os horários manualmente ao
comprar (os dois bilhetes são separados).

Roda via GitHub Actions (agendado), consulta o Google Flights através do
SerpApi para cada hub em datas de janeiro/2027, guarda o histórico em
docs/data/historico.json e, se o menor preço de algum hub cair abaixo do
teto definido, envia um email de alerta.

Diferença pras tentativas anteriores:
- Amadeus (self-service) foi desativada; Duffel exige empresa registrada
  fora do Brasil; Travelpayouts não retornou dado nem de rota popular.
- O SerpApi lê o próprio Google Flights, então cobre suas rotas de verdade,
  com voo casado (conexões), horários reais e preço para o grupo exato
  (2 adultos + 2 crianças). Não é estimativa -- é o preço que aparece no
  Google Flights.
- Plano gratuito do SerpApi: 250 buscas/mês. Este agente usa ~3-6 por dia.

Por que isso é "anônimo" na prática:
- Não é o seu navegador, não guarda cookies, não faz login em site de venda.
- Cada execução roda numa máquina efêmera do GitHub Actions, com IP novo a
  cada dia; a chamada ao Google Flights sai pelo SerpApi, não pela sua
  sessão -- não existe "sessão sua" que algum site possa usar pra subir
  preço.
"""

import os
import json
import time
import smtplib
import requests
from datetime import date, timedelta
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO -- ajuste aqui o que quiser sem mexer no resto do código
# ---------------------------------------------------------------------------

DESTINO = "MIA"       # Miami Intl. -- só voo DIRETO; Orlando (MCO) não tem
DESTINO_NOME = "Miami"

ORIGEM_DOMESTICA = "THE"   # Teresina -- de onde sai a perna doméstica até o hub

# Hubs de partida rumo a Miami (código IATA: nome amigável).
# Só ficam aqui hubs que fazem sentido pra voo DIRETO. THE (Teresina) foi
# removido: não existe voo internacional direto saindo de lá, então a busca
# nonstop nunca dá resultado -- manter só desperdiçaria cota do SerpApi.
HUBS = {
    "FOR": "Fortaleza",
    "BEL": "Belém",
    "BSB": "Brasília",
    "GRU": "São Paulo",
}

# Passageiros
ADULTOS = 2
CRIANCAS = 2

# Datas de ida testadas, com volta ~DURACAO dias depois.
# Período alvo: ~10 dias na SEGUNDA SEMANA de janeiro/2027, então as idas
# testadas se concentram na faixa 08-12/01 (voltas caem entre 18 e 22/01).
DATAS_IDA = ["2027-01-08", "2027-01-10", "2027-01-12"]
DURACAO_VIAGEM_DIAS = 10

# --- Perna doméstica Teresina -> hub -----------------------------------------
# Buscar a perna doméstica dobra o consumo de buscas. Para economizar cota,
# ela é buscada UMA vez por hub (não uma por data internacional), usando as
# datas de referência abaixo -- basta trocar aqui se quiser outro dia.
# Ida doméstica: 1 dia antes da 1ª data internacional. Volta doméstica: 1 dia
# depois do retorno internacional. Ajuste conforme sua logística real.
MONITORAR_DOMESTICO = False
# Com o monitoramento doméstico desligado, usamos estes valores de REFERÊNCIA
# (coletados na busca real de 07/07/2026) para manter o total porta a porta
# completo, sem gastar cota extra. Atualize de vez em quando rodando uma vez
# com MONITORAR_DOMESTICO = True, ou conferindo manualmente.
DOMESTICO_REFERENCIA = {
    "FOR": 7878.0,
    "BEL": 8496.0,
    "BSB": 6670.0,
    "GRU": 8125.0,
}
DATA_DOMESTICA_IDA = "2027-01-04"    # Teresina -> hub (véspera do voo internacional)
DATA_DOMESTICA_VOLTA = "2027-01-26"  # hub -> Teresina (dia seguinte ao retorno)

# Teto de preço (BRL) para disparar o alerta por email (preço total do grupo,
# considerando internacional + doméstico quando este está ativo).
# Lembre de manter o mesmo valor em docs/index.html (TETO_PRECO no JS).
TETO_PRECO_BRL = 20000.00

HIST_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "historico.json")

SERPAPI_URL = "https://serpapi.com/search"

# ---------------------------------------------------------------------------
# GOOGLE FLIGHTS (via SerpApi)
# ---------------------------------------------------------------------------

def extrair_detalhes(voo):
    """
    A partir de um objeto de voo do SerpApi (best_flights/other_flights),
    extrai o itinerário legível: cada trecho (segmento) com companhia, número
    do voo, aeroportos e horários, mais as conexões (layovers) e a duração
    total. Isso alimenta a "cascata da viagem" no painel.
    """
    if not isinstance(voo, dict):
        return None
    segmentos = []
    for seg in voo.get("flights", []) or []:
        dep = seg.get("departure_airport") or {}
        arr = seg.get("arrival_airport") or {}
        segmentos.append({
            "de": dep.get("id"),
            "de_nome": dep.get("name"),
            "partida": dep.get("time"),        # ex.: "2027-01-10 22:15"
            "para": arr.get("id"),
            "para_nome": arr.get("name"),
            "chegada": arr.get("time"),
            "cia": seg.get("airline"),
            "voo": seg.get("flight_number"),
            "duracao_min": seg.get("duration"),
        })
    layovers = []
    for lay in voo.get("layovers", []) or []:
        layovers.append({
            "aeroporto": lay.get("id"),
            "nome": lay.get("name"),
            "duracao_min": lay.get("duration"),
        })
    if not segmentos:
        return None
    return {
        "segmentos": segmentos,
        "layovers": layovers,
        "duracao_total_min": voo.get("total_duration"),
    }


def buscar_voo(origem, destino, data_ida, data_volta, apenas_direto=True):
    """
    Consulta o Google Flights para uma rota/data específica. Devolve um dict
    {"preco": float, "detalhes": {...}|None} com o menor preço do grupo (BRL)
    e o itinerário da opção de voo mais barata (para a cascata), ou None se
    não houver resultado. Os voos de ida-e-volta do Google trazem primeiro o
    trecho de IDA, então o itinerário capturado é o da ida.

    apenas_direto=True filtra só voos sem escala (stops=1 no SerpApi). Se a
    rota não tiver opção direta, o Google/SerpApi simplesmente não retorna
    nada -- não retorna voo com conexão como "melhor esforço".
    """
    params = {
        "engine": "google_flights",
        "departure_id": origem,
        "arrival_id": destino,
        "outbound_date": data_ida,
        "return_date": data_volta,
        "adults": ADULTOS,
        "children": CRIANCAS,
        "currency": "BRL",
        "hl": "pt-br",
        "gl": "br",
        "type": "1",          # 1 = ida e volta
        "travel_class": "1",  # 1 = econômica
        "api_key": os.environ["SERPAPI_KEY"],
    }
    if apenas_direto:
        params["stops"] = "1"  # 1 = somente voo direto (SerpApi google_flights)
    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=60)
    except requests.RequestException as e:
        print(f"  [aviso] {origem}->{destino} {data_ida}: erro de rede: {e}")
        return None

    if resp.status_code != 200:
        print(f"  [aviso] {origem}->{destino} {data_ida}: HTTP {resp.status_code}: {resp.text[:200]}")
        return None

    dados = resp.json()

    # O menor preço confiável costuma vir em price_insights.lowest_price;
    # senão, pegamos o menor entre best_flights + other_flights. Em paralelo,
    # guardamos o objeto de voo mais barato (com itinerário) para a cascata.
    precos = []
    insights = dados.get("price_insights") or {}
    if isinstance(insights.get("lowest_price"), (int, float)):
        precos.append(float(insights["lowest_price"]))

    voo_mais_barato = None
    preco_voo_mais_barato = None
    for chave in ("best_flights", "other_flights"):
        for voo in dados.get(chave, []) or []:
            if isinstance(voo.get("price"), (int, float)):
                p = float(voo["price"])
                precos.append(p)
                if preco_voo_mais_barato is None or p < preco_voo_mais_barato:
                    preco_voo_mais_barato = p
                    voo_mais_barato = voo

    if not precos:
        return None
    return {
        "preco": min(precos),
        # Itinerário da opção mais barata com voos listados (a ida). Pode ser
        # None se o menor preço só veio dos "insights", sem voo detalhado.
        "detalhes": extrair_detalhes(voo_mais_barato),
    }


# ---------------------------------------------------------------------------
# HISTÓRICO
# ---------------------------------------------------------------------------

def carregar_historico():
    if os.path.exists(HIST_PATH):
        with open(HIST_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def salvar_historico(historico):
    os.makedirs(os.path.dirname(HIST_PATH), exist_ok=True)
    with open(HIST_PATH, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------

def enviar_email(assunto, corpo):
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"] = os.environ["EMAIL_USER"]
    msg["To"] = os.environ["EMAIL_TO"]

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(os.environ["EMAIL_USER"], os.environ["EMAIL_PASS"])
        server.sendmail(os.environ["EMAIL_USER"], [os.environ["EMAIL_TO"]], msg.as_string())


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    historico = carregar_historico()
    hoje = date.today().isoformat()

    # 1) Perna doméstica Teresina -> hub: 1 busca por hub (economiza cota).
    #    Guardamos o preço doméstico de cada hub para somar depois.
    domestico_por_hub = {}
    if MONITORAR_DOMESTICO:
        print("--- Perna doméstica (Teresina -> hub) ---")
        for origem_hub, nome_hub in HUBS.items():
            res_dom = buscar_voo(ORIGEM_DOMESTICA, origem_hub,
                                 DATA_DOMESTICA_IDA, DATA_DOMESTICA_VOLTA)
            time.sleep(1)
            if res_dom is None:
                print(f"Teresina -> {nome_hub} ({origem_hub}): sem resultado.")
            else:
                preco_dom = res_dom["preco"]
                print(f"Teresina -> {nome_hub} ({origem_hub}): R$ {preco_dom:.2f}")
                domestico_por_hub[origem_hub] = preco_dom

    # 2) Trecho internacional hub -> Miami (só direto), por data, somando o
    #    doméstico. Se o monitoramento doméstico está desligado, usa os
    #    valores de referência fixos (sem gastar cota) pra manter o total
    #    comparável.
    if not MONITORAR_DOMESTICO:
        domestico_por_hub = dict(DOMESTICO_REFERENCIA)
        print("--- Perna doméstica: usando valores de REFERÊNCIA (sem busca) ---")

    print(f"--- Trecho internacional (hub -> {DESTINO_NOME}, só direto) + total ---")
    novos_registros = []
    for origem_hub, nome_hub in HUBS.items():
        for data_ida in DATAS_IDA:
            di = date.fromisoformat(data_ida)
            data_volta = (di + timedelta(days=DURACAO_VIAGEM_DIAS)).isoformat()

            res_intl = buscar_voo(origem_hub, DESTINO, data_ida, data_volta)
            time.sleep(1)

            if res_intl is None:
                print(f"{nome_hub} ({origem_hub}) {data_ida}: sem voo direto pra {DESTINO_NOME}.")
                continue

            preco_intl = res_intl["preco"]
            detalhes_intl = res_intl["detalhes"]

            preco_dom = domestico_por_hub.get(origem_hub)  # pode ser None
            preco_total = preco_intl + (preco_dom or 0.0)

            dom_txt = f" + dom R$ {preco_dom:.2f}" if preco_dom else " (sem doméstico)"
            print(f"{nome_hub} ({origem_hub}) {data_ida} -> {data_volta}: "
                  f"intl R$ {preco_intl:.2f}{dom_txt} = total R$ {preco_total:.2f}")

            preco_por_pax = round(preco_total / (ADULTOS + CRIANCAS), 2)

            novos_registros.append({
                "data_busca": hoje,
                "hub": origem_hub,
                "hub_nome": nome_hub,
                "data_ida": data_ida,
                "data_volta": data_volta,
                # Marca a era do registro (MIA/voo direto). Registros antigos
                # (pré-pivô, Orlando/MCO com conexão) não têm este campo --
                # o painel usa isso pra não misturar as duas eras no ranking.
                "destino": DESTINO,
                "preco_internacional_brl": preco_intl,
                "preco_domestico_brl": preco_dom,   # None se não monitorado/sem dado
                "preco_total_brl": preco_total,     # total porta a porta (ou só intl)
                # Média por passageiro (total do grupo / 4). É média mesmo:
                # o Google devolve preço do grupo, não o unitário por pessoa.
                "preco_medio_passageiro_brl": preco_por_pax,
                # Itinerário da IDA internacional (hub -> Miami, direto), p/ a
                # cascata. O trecho Teresina -> hub é valor de referência, sem voos.
                "detalhes_ida": detalhes_intl,
                "fonte": "google_flights_serpapi",
            })

    if not novos_registros:
        print("Nenhum resultado em nenhum hub hoje (verifique a chave SERPAPI_KEY ou as datas).")
        return

    novos_registros.sort(key=lambda x: x["preco_total_brl"])
    mais_barato = novos_registros[0]

    # Idempotente por dia: se já houver registros da busca de hoje (ex.: o
    # workflow rodou 2x no mesmo dia), substitui em vez de duplicar.
    historico = [r for r in historico if r.get("data_busca") != hoje]
    historico.extend(novos_registros)
    salvar_historico(historico)

    dom = mais_barato.get("preco_domestico_brl")
    detalhe_dom = (f"  (internacional R$ {mais_barato['preco_internacional_brl']:.2f} "
                   f"+ Teresina->{mais_barato['hub_nome']} R$ {dom:.2f})") if dom else \
                  "  (só trecho internacional; doméstico sem dado)"

    print(f"\nMais barato hoje (porta a porta): R$ {mais_barato['preco_total_brl']:.2f} "
          f"via {mais_barato['hub_nome']} ({mais_barato['hub']}), "
          f"{mais_barato['data_ida']} -> {mais_barato['data_volta']}")
    print(detalhe_dom)

    if mais_barato["preco_total_brl"] <= TETO_PRECO_BRL:
        linha_dom = (f"  - Teresina -> {mais_barato['hub_nome']}: R$ {dom:.2f}\n"
                     if dom else
                     "  - Teresina -> hub: sem dado hoje (some manualmente)\n")
        corpo = (
            f"Achei uma combinação rumo a {DESTINO_NOME} abaixo do teto de "
            f"R$ {TETO_PRECO_BRL:.2f} (preço total, 2 adultos + 2 crianças)!\n\n"
            f"Melhor rota hoje: Teresina -> {mais_barato['hub_nome']} "
            f"({mais_barato['hub']}) -> {DESTINO_NOME} (voo direto)\n\n"
            f"Total porta a porta: R$ {mais_barato['preco_total_brl']:.2f}\n"
            f"  - {mais_barato['hub_nome']} -> {DESTINO_NOME}: "
            f"R$ {mais_barato['preco_internacional_brl']:.2f}\n"
            f"{linha_dom}\n"
            f"Ida (internacional): {mais_barato['data_ida']}\n"
            f"Volta (internacional): {mais_barato['data_volta']}\n\n"
            f"Preços lidos do Google Flights via SerpApi (trecho internacional "
            f"sempre voo direto, sem escala). Confira se o horário do trecho "
            f"doméstico Teresina -> hub casa com o internacional e confirme no "
            f"site da companhia antes de fechar.\n"
            f"(Busca automática rodada em {hoje} via GitHub Actions)"
        )
        enviar_email(f"✈️ Combinação boa Teresina -> {DESTINO_NOME}!", corpo)
        print("Email de alerta enviado.")
    else:
        print("Preço ainda acima do teto definido. Nenhum email enviado.")


if __name__ == "__main__":
    main()
