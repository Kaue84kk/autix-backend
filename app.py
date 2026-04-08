from flask import Flask, request, jsonify
import re

app = Flask(__name__)

# =========================
# LIMPEZA DE TEXTO (OCR)
# =========================
def normalizar_texto(texto):
    texto = texto.upper()

    correcoes = {
        "ALINHAMENO": "ALINHAMENTO",
        "DIEÇÃO": "DIRECAO",
        "NEU": "PNEU",
        "GOODYEA": "GOODYEAR",
        "MONAGEM": "MONTAGEM",
        "BALANCEAMENO": "BALANCEAMENTO",
        "ESACIONAMENO": "ESTACIONAMENTO",
        "AFEIÇÃO": "AFEICAO",
        "ODA": "RODA",
        "ESILHAS": "PASTILHAS",
        "BOACHEIO": "BORRACHEIRO",
    }

    for errado, certo in correcoes.items():
        texto = texto.replace(errado, certo)

    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


# =========================
# CLASSIFICAÇÃO
# =========================
def classificar_item(nome):
    palavras_peca = ["PNEU", "KIT", "BUCHA", "PASTILHA", "SENSOR"]

    for palavra in palavras_peca:
        if palavra in nome:
            return "PECA"

    return "MAO_DE_OBRA"


# =========================
# REGRA DE DECISÃO
# =========================
def classificar_acao(diferenca):
    if diferenca < 20:
        return "IGNORAR", "BAIXA"
    elif diferenca <= 80:
        return "NEGOCIAR", "MEDIA"
    else:
        return "NEGOCIAR FORTE", "ALTA"


# =========================
# EXTRAÇÃO DE VALOR (string → float)
# =========================
def parse_valor(valor):
    if isinstance(valor, (int, float)):
        return float(valor)

    valor = valor.replace("R$", "").replace(",", "").strip()
    return float(valor)


# =========================
# CÉREBRO V6
# =========================
def analisar_v6(itens, total_oficina):
    resultado = []

    total_glosa_pecas = 0
    total_glosa_mo = 0

    for item in itens:
        nome = normalizar_texto(item.get("item", ""))

        valor_oficina = parse_valor(item.get("oficina", 0))
        valor_seguradora = parse_valor(item.get("seguradora", 0))

        diferenca = round(valor_oficina - valor_seguradora, 2)

        tipo_item = classificar_item(nome)

        # ITEM NÃO APROVADO
        if item.get("tipo") == "ITEM_NAO_APROVADO":
            impacto = valor_oficina

            if tipo_item == "PECA":
                total_glosa_pecas += impacto
            else:
                total_glosa_mo += impacto

            resultado.append({
                "item": nome,
                "tipo": "NAO_APROVADO",
                "categoria": tipo_item,
                "valor": impacto,
                "acao": "COBRAR SEGURADORA",
                "prioridade": "ALTA"
            })
            continue

        # DIVERGÊNCIA
        if diferenca <= 0:
            continue

        acao, prioridade = classificar_acao(diferenca)

        if acao == "IGNORAR":
            continue

        if tipo_item == "PECA":
            total_glosa_pecas += diferenca
        else:
            total_glosa_mo += diferenca

        resultado.append({
            "item": nome,
            "tipo": "DIVERGENCIA",
            "categoria": tipo_item,
            "oficina": valor_oficina,
            "seguradora": valor_seguradora,
            "diferenca": diferenca,
            "acao": acao,
            "prioridade": prioridade
        })

    total_glosa = round(total_glosa_pecas + total_glosa_mo, 2)
    faturamento_real = round(total_oficina - total_glosa, 2)

    # VALIDAÇÃO MATEMÁTICA
    if round(total_oficina - total_glosa, 2) != faturamento_real:
        raise Exception("ERRO MATEMÁTICO NO FECHAMENTO")

    return {
        "analise": resultado,
        "totais": {
            "glosa_pecas": total_glosa_pecas,
            "glosa_mao_de_obra": total_glosa_mo,
            "glosa_total": total_glosa
        },
        "financeiro": {
            "total_oficina": total_oficina,
            "faturamento_real": faturamento_real
        }
    }


# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.route("/analisar", methods=["POST"])
def analisar():
    try:
        data = request.json

        itens = data.get("itens", [])
        total_oficina = parse_valor(data.get("total_oficina", 0))

        resultado = analisar_v6(itens, total_oficina)

        return jsonify(resultado)

    except Exception as e:
        return jsonify({
            "erro": str(e)
        }), 500


# =========================
# START
# =========================
if __name__ == "__main__":
    app.run(debug=True)
