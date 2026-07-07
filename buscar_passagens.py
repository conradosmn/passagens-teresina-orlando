#!/usr/bin/env python3
"""
Agente de busca diária de passagens rumo a Orlando (jan/2027)
2 adultos + 2 crianças

Não existe voo Teresina -> Orlando direto. Este agente monitora os trechos
internacionais a partir dos hubs com voo para Orlando (Fortaleza, Belém e
Brasília). A perna Teresina -> hub será adicionada numa etapa seguinte; por
ora, você casa os horários manualmente ao comprar.

Roda via GitHub Actions (agendado), consulta a Travelpayouts Data API
(cache de preços do Aviasales) para janeiro/2027 em cada hub, guarda o
histórico em docs/data/historico.json e, se o indicador de algum hub cair
abaixo do teto definido, envia um email de alerta.

IMPORTANTE -- leia antes de confiar cegamente no número:
- Amadeus (self-service) foi desativada e a Duffel exige "country of
  incorporation" (empresa registrada) que não inclui o Brasil no cadastro
  --  então não dava pra usar nenhuma das duas.
- A Travelpayouts é a única opção sem barreira de KYB/empresa: cadastro
  aberto pra qualquer país, mas os dados vêm de um CACHE de buscas de
  outros usuários no Aviasales, normalmente referentes a 1 adulto -- não é
  uma cotação ao vivo pro grupo (2 adultos + 2 crianças).
- Por isso o valor salvo aqui é uma ESTIMATIVA (preço de 1 adulto x
  ESTIMATIVA_MULTIPLICADOR). Trate como indicador de tendência da rota, não
  como preço exato -- confirme sempre no site da companhia antes de comprar.
- Rota de nicho (Teresina->Orlando) pode ter pouco ou nenhum dado em cache.
  Rode manualmente uma vez (aba Actions -> Run workflow) para conferir se
  volta algo antes de confiar no histórico.

Por que isso é "anônimo" na prática:
- Não usamos navegador, não guardamos cookies, não fazemos login em site
  nenhum de venda de passagem.
- Cada execução roda numa máquina efêmera do GitHub Actions, com IP novo
  a cada dia -- não existe "sessão" associada a você que algum site possa
  usar para subir preço.
"""

import os
import json
import smtplib
import requests
from datetime import date
from email.mime.text import MIMEText

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO -- ajuste aqui o que quiser sem mexer no resto do código
# ---------------------------------------------------------------------------

# Não há voo Teresina -> Orlando direto. Monitoramos os trechos internacionais
# a partir dos hubs com voo pra Orlando. A perna Teresina -> hub será adicionada
# numa etapa seguinte (aí você casa os horários na hora de comprar).
DESTINO = "MCO"      # Orlando (Orlando Intl.) -- pode trocar p/ "MIA" se quiser comparar

# Hubs de partida rumo a Orlando (origem: nome amigável)
HUBS = {
    "FOR": "Fortaleza",
    "BEL": "Belém",
    "BSB": "Brasília",
}

MES_BUSCA = "2027-01-01"  # mês de referência (a API devolve o preço mais barato por dia do mês)

# Multiplicador aproximado pra estimar o total da família a partir do preço
# de 1 adulto que a API devolve. 2 adultos + 2 crianças ~ 3.5x o preço de 1
# adulto é um chute conservador (crianças costumam pagar menos) -- ajuste
# conforme for comparando com cotações reais.
ESTIMATIVA_MULTIPLICADOR = 3.5

# Teto de preço (BRL) para disparar o alerta por email, já pensado como
# ESTIMATIVA do total da família. Ajuste conforme calibrar com cotações
# reais. Lembre de manter o mesmo valor em docs/index.html (TETO_PRECO no JS).
TETO_PRECO_BRL = 12000.00

HIST_PATH = os.path.join(os.path.dirname(__file__), "docs", "data", "historico.json")

# ---------------------------------------------------------------------------
# TRAVELPAYOUTS SEARCH
# ---------------------------------------------------------------------------

def buscar_precos_mes(origem):
    """Consulta o preço mais barato por dia de partida no mês, para uma origem."""
    resp = requests.get(
        "https://api.travelpayouts.com/v2/prices/month-matrix",
        params={
            "currency": "BRL",
            "origin": origem,
            "destination": DESTINO,
            "month": MES_BUSCA,
            "show_to_affiliates": "true",
        },
        headers={"x-access-token": os.environ["TRAVELPAYOUTS_TOKEN"]},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"  [aviso] {origem}->{DESTINO}: HTTP {resp.status_code}: {resp.text[:200]}")
        return []
    corpo = resp.json()
    if not corpo.get("success", True):
        print(f"  [aviso] {origem}->{DESTINO}: success=false: {corpo}")
        return []
    return corpo.get("data", [])


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
        dias = buscar_precos_mes(origem)
        if not dias:
            print(f"{nome_hub} ({origem}): sem dado em cache hoje.")
            continue
        for dia in dias:
            preco_adulto = dia.get("price")
            data_ida = dia.get("depart_date") or dia.get("date")
            if preco_adulto is None or data_ida is None:
                continue
            novos_registros.append({
                "data_busca": hoje,
                "hub": origem,
                "hub_nome": nome_hub,
                "data_ida": data_ida,
                "preco_adulto_brl": float(preco_adulto),
                "preco_estimado_familia_brl": float(preco_adulto) * ESTIMATIVA_MULTIPLICADOR,
                "fonte": "travelpayouts_cache",
            })

    if not novos_registros:
        print("Nenhum dado em nenhum hub hoje (rota de nicho pode não ter cache, ou token inválido).")
        return

    novos_registros.sort(key=lambda x: x["preco_estimado_familia_brl"])
    mais_barato = novos_registros[0]

    historico.extend(novos_registros)
    salvar_historico(historico)

    print(f"Estimativa mais barata hoje: R$ {mais_barato['preco_estimado_familia_brl']:.2f} "
          f"via {mais_barato['hub_nome']} ({mais_barato['hub']}), ida {mais_barato['data_ida']}, "
          f"base 1 adulto R$ {mais_barato['preco_adulto_brl']:.2f}")

    if mais_barato["preco_estimado_familia_brl"] <= TETO_PRECO_BRL:
        corpo = (
            f"O indicador de preço rumo a Orlando caiu abaixo do teto de "
            f"R$ {TETO_PRECO_BRL:.2f} (estimativa para 2 adultos + 2 crianças)!\n\n"
            f"Melhor hub hoje: {mais_barato['hub_nome']} ({mais_barato['hub']}) -> Orlando\n"
            f"Estimativa do total da família: R$ {mais_barato['preco_estimado_familia_brl']:.2f}\n"
            f"Preço-base (1 adulto, cache Aviasales): R$ {mais_barato['preco_adulto_brl']:.2f}\n"
            f"Data de ida sinalizada: {mais_barato['data_ida']}\n\n"
            f"Lembre: falta a perna Teresina -> {mais_barato['hub_nome']}, que ainda não é "
            f"monitorada. Some esse trecho e confira se os horários casam antes de comprar.\n\n"
            f"ATENÇÃO: isso é uma ESTIMATIVA baseada em cache de buscas de outros usuários, "
            f"não uma cotação ao vivo pro seu grupo. Confirme o preço real no site da "
            f"companhia ou numa agência antes de decidir.\n\n"
            f"(Busca automática rodada em {hoje} via GitHub Actions)"
        )
        enviar_email("✈️ Indicador de preço bom rumo a Orlando!", corpo)
        print("Email de alerta enviado.")
    else:
        print("Estimativa ainda acima do teto definido. Nenhum email enviado.")


if __name__ == "__main__":
    main()


