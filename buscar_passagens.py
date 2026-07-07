#!/usr/bin/env python3
"""
Agente de busca diária de passagens rumo a Orlando (jan/2027)
2 adultos + 2 crianças -- preço REAL do grupo, via Google Flights (SerpApi).

Não existe voo Teresina -> Orlando direto. Este agente monitora os trechos
internacionais a partir dos hubs com voo para Orlando (Fortaleza, Belém e
Brasília). A perna Teresina -> hub será adicionada numa etapa seguinte; por
ora, você casa os horários manualmente ao comprar.

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

DESTINO = "MCO"      # Orlando (Orlando Intl.) -- pode trocar p/ "MIA" se quiser comparar

ORIGEM_DOMESTICA = "THE"   # Teresina -- de onde sai a perna doméstica até o hub

# Hubs de partida rumo a Orlando (código IATA: nome amigável).
# THE (Teresina direto) é um teste: o Google Flights monta as conexões
# sozinho (via FOR/BSB/GRU etc.) num bilhete só, com horários que casam.
# Se der bom resultado, pode aposentar a lógica de somar trechos separados.
HUBS = {
    "THE": "Teresina (direto/conexão auto)",
    "FOR": "Fortaleza",
    "BEL": "Belém",
    "BSB": "Brasília",
    "GRU": "São Paulo",
}

# Passageiros
ADULTOS = 2
CRIANCAS = 2

# Datas de ida testadas dentro de janeiro/2027, com volta ~DURACAO dias depois.
# Cada data testada = 1 busca por hub (trecho internacional).
DATAS_IDA = ["2027-01-05", "2027-01-10", "2027-01-15"]
DURACAO_VIAGEM_DIAS = 10

# --- Perna doméstica Teresina -> hub -----------------------------------------
# Buscar a perna doméstica dobra o consumo de buscas. Para economizar cota,
# ela é buscada UMA vez por hub (não uma por data internacional), usando as
# datas de referência abaixo -- basta trocar aqui se quiser outro dia.
# Ida doméstica: 1 dia antes da 1ª data internacional. Volta doméstica: 1 dia
# depois do retorno internacional. Ajuste conforme sua logística real.
MONITORAR_DOMESTICO = True
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

def buscar_voo(origem, destino, data_ida, data_volta):
    """
    Consulta o Google Flights para uma rota/data específica e devolve o menor
    preço encontrado (total do grupo, em BRL) ou None se não houver resultado.
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
    # senão, pegamos o menor entre best_flights + other_flights.
    precos = []
    insights = dados.get("price_insights") or {}
    if isinstance(insights.get("lowest_price"), (int, float)):
        precos.append(float(insights["lowest_price"]))

    for chave in ("best_flights", "other_flights"):
        for voo in dados.get(chave, []) or []:
            if isinstance(voo.get("price"), (int, float)):
                precos.append(float(voo["price"]))

    if not precos:
        return None
    return min(precos)


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
            if origem_hub == ORIGEM_DOMESTICA:
                continue  # THE direto não tem perna doméstica (é a própria origem)
            preco_dom = buscar_voo(ORIGEM_DOMESTICA, origem_hub,
                                   DATA_DOMESTICA_IDA, DATA_DOMESTICA_VOLTA)
            time.sleep(1)
            if preco_dom is None:
                print(f"Teresina -> {nome_hub} ({origem_hub}): sem resultado.")
            else:
                print(f"Teresina -> {nome_hub} ({origem_hub}): R$ {preco_dom:.2f}")
                domestico_por_hub[origem_hub] = preco_dom

    # 2) Trecho internacional hub -> Orlando, por data, somando o doméstico.
    print("--- Trecho internacional (hub -> Orlando) + total ---")
    novos_registros = []
    for origem_hub, nome_hub in HUBS.items():
        for data_ida in DATAS_IDA:
            di = date.fromisoformat(data_ida)
            data_volta = (di + timedelta(days=DURACAO_VIAGEM_DIAS)).isoformat()

            preco_intl = buscar_voo(origem_hub, DESTINO, data_ida, data_volta)
            time.sleep(1)

            if preco_intl is None:
                print(f"{nome_hub} ({origem_hub}) {data_ida}: sem resultado internacional.")
                continue

            preco_dom = domestico_por_hub.get(origem_hub)  # pode ser None
            preco_total = preco_intl + (preco_dom or 0.0)

            dom_txt = f" + dom R$ {preco_dom:.2f}" if preco_dom else " (sem doméstico)"
            print(f"{nome_hub} ({origem_hub}) {data_ida} -> {data_volta}: "
                  f"intl R$ {preco_intl:.2f}{dom_txt} = total R$ {preco_total:.2f}")

            novos_registros.append({
                "data_busca": hoje,
                "hub": origem_hub,
                "hub_nome": nome_hub,
                "data_ida": data_ida,
                "data_volta": data_volta,
                "preco_internacional_brl": preco_intl,
                "preco_domestico_brl": preco_dom,   # None se não monitorado/sem dado
                "preco_total_brl": preco_total,     # total porta a porta (ou só intl)
                "fonte": "google_flights_serpapi",
            })

    if not novos_registros:
        print("Nenhum resultado em nenhum hub hoje (verifique a chave SERPAPI_KEY ou as datas).")
        return

    novos_registros.sort(key=lambda x: x["preco_total_brl"])
    mais_barato = novos_registros[0]

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
            f"Achei uma combinação rumo a Orlando abaixo do teto de "
            f"R$ {TETO_PRECO_BRL:.2f} (preço total, 2 adultos + 2 crianças)!\n\n"
            f"Melhor rota hoje: Teresina -> {mais_barato['hub_nome']} "
            f"({mais_barato['hub']}) -> Orlando\n\n"
            f"Total porta a porta: R$ {mais_barato['preco_total_brl']:.2f}\n"
            f"  - {mais_barato['hub_nome']} -> Orlando: "
            f"R$ {mais_barato['preco_internacional_brl']:.2f}\n"
            f"{linha_dom}\n"
            f"Ida (internacional): {mais_barato['data_ida']}\n"
            f"Volta (internacional): {mais_barato['data_volta']}\n\n"
            f"Preços lidos do Google Flights via SerpApi (trechos comprados "
            f"separadamente). Confira se os horários das conexões casam e "
            f"confirme no site da companhia antes de fechar.\n"
            f"(Busca automática rodada em {hoje} via GitHub Actions)"
        )
        enviar_email("✈️ Combinação boa Teresina -> Orlando!", corpo)
        print("Email de alerta enviado.")
    else:
        print("Preço ainda acima do teto definido. Nenhum email enviado.")


if __name__ == "__main__":
    main()
