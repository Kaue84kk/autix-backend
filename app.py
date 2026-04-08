from flask import Flask, request, jsonify
import pdfplumber
import re
import os

app = Flask(__name__)

# =========================
# UTIL
# =========================
def limpar_valor(valor):
    try:
        valor = str(valor).replace("R$", "").replace(".", "").replace(",", ".").strip()
        return float(valor)
    except:
        return 0.0


def normalizar(txt):
    if not txt:
        return ""
    return re.sub(r'\s+', ' ', txt.upper()).strip()


# =========================
# EXTRAÇÃO PDF
# =========================
def extrair_itens(pdf_file):
    itens = []
    texto_total = ""

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto_total += page.extract_text() + "\n"

    linhas = texto_total.split("\n")

    for linha in linhas:
        linha = normalizar(linha)

        # PEÇAS (com preço)
        match = re.search(r'(.*?) (OFICINA|SEGURADORA) R\$ ([\d\.,]+)', linha)
        if match:
            nome = match.group(1)
            fornecimento = match.group(2)
            valor = limpar_valor(match.group(3))

            itens.append({
                "descricao": nome,
                "fornecimento": fornecimento,
                "valor": valor,
                "tipo": "PECA"
            })

        # MÃO DE OBRA (R&I, R, P)
        match_mo = re.search(r'(R&I|R |P ) ([\d\.,]+)', linha)
        if match_mo:
            tipo = match_mo.group(1).strip()
            horas = float(match_mo.group(2).replace(",", "."))

            itens.append({
                "descricao": linha,
                "tipo": "MAO_DE_OBRA",
                "subtipo": tipo,
                "horas": horas
            })

    return itens


# =========================
# MATCH
# =========================
def match_itens(itens_oficina, itens_seg):
    pares = []

    for item_o in itens_oficina:
        melhor = None

        for item_s in itens_seg:
            if item_o["descricao"][:15] in item_s["descricao"]:
                melhor = item_s
                break

        pares.append((item_o, melhor))

    return pares


# =========================
# CÉREBRO V6 (REAL)
# =========================
def analisar(pares):
    divergencias = []

    for oficina, seguradora in pares:

        # PEÇAS
        if oficina["tipo"] == "PECA":

            if not seguradora:
                divergencias.append({
                    "tipo": "PECA_REMOVIDA",
                    "descricao": oficina["descricao"],
                    "alerta": "Peça removida — validar vistoria"
                })
                continue

            # mudança de fornecimento
            if oficina["fornecimento"] != seguradora["fornecimento"]:
                divergencias.append({
                    "tipo": "MUDANCA_FORNECIMENTO",
                    "descricao": oficina["descricao"],
                    "oficina": oficina["fornecimento"],
                    "seguradora": seguradora["fornecimento"]
                })

            # glosa oficina
            if oficina["fornecimento"] == "OFICINA":
                if seguradora["valor"] < oficina["valor"]:
                    divergencias.append({
                        "tipo": "GLOSA_PECA",
                        "descricao": oficina["descricao"],
                        "oficina": oficina["valor"],
                        "seguradora": seguradora["valor"],
                        "diferenca": round(oficina["valor"] - seguradora["valor"], 2)
                    })

        # MÃO DE OBRA
        if oficina["tipo"] == "MAO_DE_OBRA" and seguradora:

            if seguradora["horas"] < oficina["horas"]:
                divergencias.append({
                    "tipo": "GLOSA_MO",
                    "descricao": oficina["descricao"],
                    "tipo_mo": oficina["subtipo"],
                    "oficina": oficina["horas"],
                    "seguradora": seguradora["horas"],
                    "diferenca": round(oficina["horas"] - seguradora["horas"], 2)
                })

    return divergencias


# =========================
# LÍQUIDO
# =========================
def extrair_liquido(pdf_file):
    texto = ""

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text()

    match = re.search(r'LÍQUIDO GERAL.*?R\$ ([\d\.,]+)', texto)

    if match:
        return limpar_valor(match.group(1))

    return 0.0


# =========================
# ENDPOINT
# =========================
@app.route("/analisar", methods=["POST"])
def analisar_endpoint():
    try:
        pdf_oficina = request.files["oficina"]
        pdf_seguradora = request.files["seguradora"]

        itens_oficina = extrair_itens(pdf_oficina)
        itens_seg = extrair_itens(pdf_seguradora)

        pares = match_itens(itens_oficina, itens_seg)

        divergencias = analisar(pares)

        liquido_oficina = extrair_liquido(pdf_oficina)
        liquido_seg = extrair_liquido(pdf_seguradora)

        diferenca = round(liquido_oficina - liquido_seg, 2)

        return jsonify({
            "divergencias": divergencias,
            "resultado_financeiro": {
                "oficina": liquido_oficina,
                "seguradora": liquido_seg,
                "diferenca": diferenca
            }
        })

    except Exception as e:
        return jsonify({"erro": str(e)}), 500


# =========================
# RAILWAY
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
