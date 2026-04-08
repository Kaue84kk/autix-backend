from flask import Flask, request, jsonify
import re

app = Flask(__name__)

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
    }

    for errado, certo in correcoes.items():
        texto = texto.replace(errado, certo)

    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


def classificar_item(nome):
    palavras_peca = ["PNEU", "KIT", "BUCHA", "PASTILHA", "SENSOR"]

    for palavra in palavras_peca:
        if palavra in nome:
            return "PECA"

    return "MAO_DE_OBRA"


def parse_valor(valor):
    if isinstance(valor, (int, float)):
        return float(valor)

    valor = valor.replace("R$", "").replace(",", "").strip()
    return float(valor)


def analisar(itens):
    divergencias = []

    for item in itens:
        nome = normalizar_texto(item.get("item", ""))

        valor_oficina = parse_valor(item.get("oficina", 0))
        valor_seguradora = parse_valor(item.get("seguradora", 0))

        categoria = classificar_item(nome)

        # ITEM NÃO APROVADO
        if item.get("tipo") == "ITEM_NAO_APROVADO":
            divergencias.append({
                "tipo": "ITEM_NAO_APROVADO",
                "categoria": categoria,
                "item": nome,
                "valor": valor_oficina
            })
            continue

        # VALOR ALTERADO
        if round(valor_oficina, 2) != round(valor_seguradora, 2):
            divergencias.append({
                "tipo": "VALOR_ALTERADO",
                "categoria": categoria,
                "item": nome,
                "oficina": valor_oficina,
                "seguradora": valor_seguradora,
                "diferenca": round(valor_oficina - valor_seguradora, 2)
            })

    return {
        "divergencias": divergencias
    }


@app.route("/analisar", methods=["POST"])
def analisar_endpoint():
    try:
        data = request.json
        itens = data.get("itens", [])

        resultado = analisar(itens)

        return jsonify(resultado)

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)
