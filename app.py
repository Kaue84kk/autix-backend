from flask import Flask, request, jsonify, render_template_string
import pdfplumber
import re
import io

app = Flask(__name__)

# =========================
# TELA WEB (AGORA VAI ABRIR!)
# =========================
HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Autix</title>
</head>
<body>
    <h2>Autix - Análise de Orçamento</h2>
    <form action="/analisar" method="post" enctype="multipart/form-data">
        <p>PDF Oficina:</p>
        <input type="file" name="oficina" required><br><br>

        <p>PDF Seguradora:</p>
        <input type="file" name="seguradora" required><br><br>

        <button type="submit">Analisar</button>
    </form>
</body>
</html>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

# =========================
# FUNÇÕES
# =========================
def limpar_valor(valor):
    try:
        valor = str(valor).replace("R$", "").replace(".", "").replace(",", ".")
        return float(valor)
    except:
        return 0.0

def normalizar(txt):
    return re.sub(r'\s+', ' ', txt.upper()).strip()

def extrair_texto(pdf_file):
    texto = ""
    pdf_bytes = pdf_file.read()
    pdf_stream = io.BytesIO(pdf_bytes)

    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            conteudo = page.extract_text()
            if conteudo:
                texto += conteudo + "\n"

    return texto

def extrair_itens(texto):
    itens = []
    linhas = texto.split("\n")

    for linha in linhas:
        linha = normalizar(linha)

        if "R$" in linha and ("OFICINA" in linha or "SEGURADORA" in linha):
            try:
                valor = limpar_valor(linha.split("R$")[-1])
                fornecimento = "OFICINA" if "OFICINA" in linha else "SEGURADORA"

                itens.append({
                    "descricao": linha,
                    "fornecimento": fornecimento,
                    "valor": valor
                })
            except:
                continue

    return itens

def analisar(itens_o, itens_s):
    divergencias = []

    for o in itens_o:
        match = None

        for s in itens_s:
            if o["descricao"][:20] in s["descricao"]:
                match = s
                break

        if not match:
            divergencias.append({
                "tipo": "PECA_REMOVIDA",
                "descricao": o["descricao"]
            })
            continue

        if o["fornecimento"] != match["fornecimento"]:
            divergencias.append({
                "tipo": "MUDANCA_FORNECIMENTO",
                "descricao": o["descricao"]
            })

        if o["fornecimento"] == "OFICINA":
            if match["valor"] < o["valor"]:
                divergencias.append({
                    "tipo": "GLOSA",
                    "descricao": o["descricao"],
                    "diferenca": round(o["valor"] - match["valor"], 2)
                })

    return divergencias

def extrair_liquido(texto):
    match = re.search(r'L[ÍI]QUIDO GERAL.*?R\$ ([\d\.,]+)', texto)
    return limpar_valor(match.group(1)) if match else 0

# =========================
# ANÁLISE
# =========================
@app.route("/analisar", methods=["POST"])
def analisar_endpoint():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    texto_o = extrair_texto(pdf_o)
    texto_s = extrair_texto(pdf_s)

    itens_o = extrair_itens(texto_o)
    itens_s = extrair_itens(texto_s)

    divergencias = analisar(itens_o, itens_s)

    liquido_o = extrair_liquido(texto_o)
    liquido_s = extrair_liquido(texto_s)

    return jsonify({
        "divergencias": divergencias,
        "financeiro": {
            "oficina": liquido_o,
            "seguradora": liquido_s,
            "diferenca": liquido_o - liquido_s
        }
    })
