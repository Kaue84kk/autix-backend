from flask import Flask, request, jsonify, render_template_string
import pdfplumber
import io
import re

app = Flask(__name__)

# =========================
# HTML SIMPLES
# =========================
HTML = """
<h2>AUTIX - Análise de Orçamento</h2>

<form action="/analisar" method="post" enctype="multipart/form-data">
    <p>PDF Oficina:</p>
    <input type="file" name="oficina" required><br><br>

    <p>PDF Seguradora:</p>
    <input type="file" name="seguradora" required><br><br>

    <button type="submit">Analisar</button>
</form>
"""

# =========================
# HOME
# =========================
@app.route("/")
def home():
    return render_template_string(HTML)

# =========================
# LIMPAR VALOR
# =========================
def limpar_valor(valor):
    try:
        return float(valor.replace("R$", "").replace(".", "").replace(",", "."))
    except:
        return 0.0

# =========================
# EXTRAIR TEXTO PDF (CORRIGIDO)
# =========================
def extrair_texto(pdf_file):
    texto = ""

    try:
        pdf_bytes = pdf_file.read()
        pdf_stream = io.BytesIO(pdf_bytes)

        with pdfplumber.open(pdf_stream) as pdf:
            for page in pdf.pages:
                conteudo = page.extract_text()
                if conteudo:
                    texto += conteudo + "\n"

    except Exception as e:
        print("ERRO AO LER PDF:", str(e))
        return ""

    return texto

# =========================
# EXTRAIR LIQUIDO (ROBUSTO)
# =========================
def extrair_liquido(texto):
    texto = texto.upper()

    padroes = [
        r"L[ÍI]QUIDO GERAL.*?R\$ ?([\d\.,]+)",
        r"TOTAL L[ÍI]QUIDO.*?R\$ ?([\d\.,]+)",
        r"VALOR L[ÍI]QUIDO.*?R\$ ?([\d\.,]+)",
        r"TOTAL.*?R\$ ?([\d\.,]+)"
    ]

    for padrao in padroes:
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            return limpar_valor(match.group(1))

    return 0.0

# =========================
# ENDPOINT PRINCIPAL
# =========================
@app.route("/analisar", methods=["POST"])
def analisar():
    try:
        if "oficina" not in request.files or "seguradora" not in request.files:
            return jsonify({"erro": "Envie os dois PDFs"}), 400

        pdf_o = request.files["oficina"]
        pdf_s = request.files["seguradora"]

        texto_o = extrair_texto(pdf_o)
        texto_s = extrair_texto(pdf_s)

        liquido_o = extrair_liquido(texto_o)
        liquido_s = extrair_liquido(texto_s)

        return jsonify({
            "oficina": liquido_o,
            "seguradora": liquido_s,
            "diferenca": round(liquido_o - liquido_s, 2)
        })

    except Exception as e:
        print("ERRO GERAL:", str(e))
        return jsonify({"erro": str(e)}), 500
