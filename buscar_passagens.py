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

# Hubs de partida rumo a Orlando (código IATA: nome amigável).
HUBS = {
    "FOR": "Fortaleza",
    "BEL": "Belém",
    "BSB": "Brasília",
}

# Passageiros
ADULTOS = 2
CRIANCAS = 2

# Datas de ida testadas dentro de janeiro/2027, com volta ~DURACAO dias depois.
# Cada data testada = 1 busca por hub. Mantenha a lista enxuta pra não gastar
# a cota gratuita à toa (nº de buscas/dia = len(HUBS) x len(DATAS_IDA)).
DATAS_IDA = ["2027-01-05", "2027-01-10", "2027-01-15"]
DURACAO_VIAGEM_DIAS = 10

# Teto de preço (BRL) para disparar o alerta por email (preço total do grupo).
# Lembre de manter o mesmo valor em docs/index.html (TETO_PRECO no JS).
TETO_PRECO_BRL = 12000.00

HIST_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "historico.json")

SERPAPI_URL = "https://serpapi.com/search"

# ---------------------------------------------------------------------------
# GOOGLE FLIGHTS (via SerpApi)
# ---------------------------------------------------------------------------

def buscar_voo(origem, data_ida, data_volta):
    """
    Consulta o Google Flights para uma rota/data específica e devolve o menor
    preço encontrado (total do grupo, em BRL) ou None se não houver resultado.
    """
    params = {
        "engine": "google_flights",
        "departure_id": origem,
        "arrival_id": DESTINO,
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
        print(f"  [aviso] {origem} {data_ida}: erro de rede: {e}")
        return None

    if resp.status_code != 200:
        print(f"  [aviso] {origem} {data_ida}: HTTP {resp.status_code}: {resp.text[:200]}")
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

    novos_registros = []
    for origem, nome_hub in HUBS.items():
        for data_ida in DATAS_IDA:
            di = date.fromisoformat(data_ida)
            data_volta = (di + timedelta(days=DURACAO_VIAGEM_DIAS)).isoformat()

            preco = buscar_voo(origem, data_ida, data_volta)
            time.sleep(1)  # respiro entre chamadas

            if preco is None:
                print(f"{nome_hub} ({origem}) {data_ida}: sem resultado.")
                continue

            print(f"{nome_hub} ({origem}) {data_ida} -> {data_volta}: R$ {preco:.2f}")
            novos_registros.append({
                "data_busca": hoje,
                "hub": origem,
                "hub_nome": nome_hub,
                "data_ida": data_ida,
                "data_volta": data_volta,
                "preco_total_brl": preco,
                "fonte": "google_flights_serpapi",
            })

    if not novos_registros:
        print("Nenhum resultado em nenhum hub hoje (verifique a chave SERPAPI_KEY ou as datas).")
        return

    novos_registros.sort(key=lambda x: x["preco_total_brl"])
    mais_barato = novos_registros[0]

    historico.extend(novos_registros)
    salvar_historico(historico)

    print(f"\nMais barato hoje: R$ {mais_barato['preco_total_brl']:.2f} "
          f"via {mais_barato['hub_nome']} ({mais_barato['hub']}), "
          f"{mais_barato['data_ida']} -> {mais_barato['data_volta']}")

    if mais_barato["preco_total_brl"] <= TETO_PRECO_BRL:
        corpo = (
            f"Achei uma passagem rumo a Orlando abaixo do teto de "
            f"R$ {TETO_PRECO_BRL:.2f} (preço total, 2 adultos + 2 crianças)!\n\n"
            f"Melhor hub hoje: {mais_barato['hub_nome']} ({mais_barato['hub']}) -> Orlando\n"
            f"Preço total do grupo: R$ {mais_barato['preco_total_brl']:.2f}\n"
            f"Ida: {mais_barato['data_ida']}\n"
            f"Volta: {mais_barato['data_volta']}\n\n"
            f"Lembre: falta a perna Teresina -> {mais_barato['hub_nome']}, que ainda "
            f"não é monitorada. Some esse trecho e confira se os horários casam "
            f"antes de comprar.\n\n"
            f"Preço lido do Google Flights via SerpApi. Confirme no site da "
            f"companhia antes de fechar.\n"
            f"(Busca automática rodada em {hoje} via GitHub Actions)"
        )
        enviar_email("✈️ Passagem boa rumo a Orlando!", corpo)
        print("Email de alerta enviado.")
    else:
        print("Preço ainda acima do teto definido. Nenhum email enviado.")


if __name__ == "__main__":
    main()
