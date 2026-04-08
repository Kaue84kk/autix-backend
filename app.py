from flask import Flask, request, render_template_string
import pdfplumber
import io
import re

app = Flask(__name__)

HTML = """
<h2>AUTIX - Análise de Orçamento</h2>

<form action="/analisar" method="post" enctype="multipart/form-data">
    <p><b>PDF Oficina:</b></p>
    <input type="file" name="oficina" required><br><br>

    <p><b>PDF Seguradora:</b></p>
    <input type="file" name="seguradora" required><br><br>

    <button type="submit">Analisar</button>
</form>
"""

@app.route("/")
def home():
    return render_template_string(HTML)

def limpar_valor(valor):
    try:
        return float(valor.replace("R$", "").replace(".", "").replace(",", "."))
    except:
        return 0.0

def normalizar(txt):
    return re.sub(r'\s+', ' ', txt.upper()).strip()

def limpar_descricao(desc):
    desc = normalizar(desc)

    desc = re.sub(r"T\s*\d+[,\.]\d+", "", desc)
    desc = re.sub(r"P\s*\d+[,\.]\d+", "", desc)
    desc = re.sub(r"\b\d{1}\b", "", desc)
    desc = re.sub(r"\b\d{5,}\b", "", desc)

    desc = desc.split("OFICINA")[0]
    desc = desc.split("R$")[0]

    return desc.strip()

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
        linha_norm = normalizar(linha)

        if any(p in linha_norm for p in [
            "TOTAL", "LIQUIDO", "BRUTO", "DESCONTO",
            "FUNILARIA", "PINTURA", "MECANICA",
            "SERVICOS", "TAPEÇARIA"
        ]):
            continue

        if "R$" in linha_norm and re.search(r"\d{5,}", linha_norm):
            try:
                valor = limpar_valor(linha_norm.split("R$")[-1])

                fornecimento = "SEGURADORA"
                if "OFICINA" in linha_norm:
                    fornecimento = "OFICINA"

                itens.append({
                    "descricao": limpar_descricao(linha_norm),
                    "valor": valor,
                    "fornecimento": fornecimento
                })

            except:
                continue

    return itens

def encontrar_match(item, lista):
    for outro in lista:
        if item["descricao"][:20] in outro["descricao"]:
            return outro
    return None

def analisar_v6(itens_o, itens_s):
    glosas = []
    removidas = []

    for item_o in itens_o:
        item_s = encontrar_match(item_o, itens_s)

        if not item_s:
            removidas.append(item_o["descricao"])
            continue

        if item_o["fornecimento"] == "OFICINA":
            if item_s["valor"] < item_o["valor"]:
                glosas.append({
                    "descricao": item_o["descricao"],
                    "oficina": item_o["valor"],
                    "seguradora": item_s["valor"],
                    "diferenca": round(item_o["valor"] - item_s["valor"], 2)
                })

    return glosas, removidas

def extrair_liquido(texto):
    texto = texto.upper()

    padroes = [
        r"L[ÍI]QUIDO GERAL.*?R\$ ?([\d\.,]+)",
        r"TOTAL.*?R\$ ?([\d\.,]+)"
    ]

    for padrao in padroes:
        match = re.search(padrao, texto, re.DOTALL)
        if match:
            return limpar_valor(match.group(1))

    return 0.0

@app.route("/analisar", methods=["POST"])
def analisar():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    texto_o = extrair_texto(pdf_o)
    texto_s = extrair_texto(pdf_s)

    itens_o = extrair_itens(texto_o)
    itens_s = extrair_itens(texto_s)

    glosas, removidas = analisar_v6(itens_o, itens_s)

    liquido_o = extrair_liquido(texto_o)
    liquido_s = extrair_liquido(texto_s)
    diferenca = round(liquido_o - liquido_s, 2)

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:red;">🔴 GLOSAS IDENTIFICADAS</h3>
    <ul>
    {% for g in glosas %}
        <li>
        <b>{{g.descricao}}</b><br>
        Oficina: R$ {{g.oficina}} | Seguradora: R$ {{g.seguradora}}<br>
        Diferença: <b>R$ {{g.diferenca}}</b>
        </li><br>
    {% endfor %}
    </ul>

    <h3 style="color:orange;">🟡 PEÇAS REMOVIDAS</h3>
    <ul>
    {% for r in removidas %}
        <li>{{r}}</li>
    {% endfor %}
    </ul>

    <h3 style="color:green;">💰 RESULTADO FINANCEIRO</h3>
    <p>Oficina: R$ {{oficina}}</p>
    <p>Seguradora: R$ {{seguradora}}</p>
    <p><b>Diferença: R$ {{diferenca}}</b></p>

    <br><br>
    <a href="/">⬅ Voltar</a>
    """,
    glosas=glosas,
    removidas=removidas,
    oficina=liquido_o,
    seguradora=liquido_s,
    diferenca=diferenca
    )
