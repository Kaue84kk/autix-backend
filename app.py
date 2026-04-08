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

# 🔥 PEÇAS (mantido)
def limpar_descricao(desc):
    desc = normalizar(desc)
    desc = re.sub(r"\b\d{5,}\b", "", desc)
    desc = desc.split("OFICINA")[0]
    desc = desc.split("R$")[0]
    return desc.strip()

def extrair_itens(texto):
    itens = []
    for linha in texto.split("\n"):
        linha_norm = normalizar(linha)

        if "R$" in linha_norm and re.search(r"\d{5,}", linha_norm):
            valor = limpar_valor(linha_norm.split("R$")[-1])

            fornecimento = "SEGURADORA"
            if "OFICINA" in linha_norm:
                fornecimento = "OFICINA"

            itens.append({
                "descricao": limpar_descricao(linha_norm),
                "valor": valor,
                "fornecimento": fornecimento
            })

    return itens

def encontrar_match(item, lista):
    for outro in lista:
        if item["descricao"][:20] in outro["descricao"]:
            return outro
    return None

def analisar_pecas(itens_o, itens_s):
    glosas = []
    removidas = []

    for item_o in itens_o:
        item_s = encontrar_match(item_o, itens_s)

        if not item_s:
            removidas.append(item_o["descricao"])
            continue

        if item_o["valor"] > item_s["valor"]:
            glosas.append({
                "descricao": item_o["descricao"],
                "oficina": item_o["valor"],
                "seguradora": item_s["valor"],
                "diferenca": round(item_o["valor"] - item_s["valor"], 2)
            })

    return glosas, removidas

# 🔥 NOVO: SERVIÇOS (MÃO DE OBRA REAL)
def extrair_servicos(texto):
    servicos = []

    for linha in texto.split("\n"):
        linha_norm = normalizar(linha)

        if linha_norm.startswith(("R&I", "R ", "P ")):
            try:
                nome = re.sub(r"R&I|R|P|\d+[,\.]\d+", "", linha_norm)
                nome = nome.strip()

                valor = re.findall(r"\d+[,\.]\d+", linha_norm)
                valor = float(valor[0].replace(",", ".")) if valor else 0

                servicos.append({
                    "descricao": nome,
                    "valor": valor
                })
            except:
                continue

    return servicos

def comparar_servicos(serv_o, serv_s):
    divergencias = []

    for s_o in serv_o:
        for s_s in serv_s:
            if s_o["descricao"][:25] in s_s["descricao"]:
                if s_o["valor"] > s_s["valor"]:
                    divergencias.append({
                        "descricao": s_o["descricao"],
                        "oficina": s_o["valor"],
                        "seguradora": s_s["valor"],
                        "diferenca": round(s_o["valor"] - s_s["valor"], 2)
                    })

    return divergencias

# 🔥 CORREÇÃO REAL: MÃO DE OBRA TOTAL
def extrair_mao_de_obra_total(texto):
    match = re.search(r"L[ÍI]QUIDO DE MÃO DE OBRA\s*\+\s*R\$ ?([\d\.,]+)", texto.upper())
    if match:
        return limpar_valor(match.group(1))
    return 0.0

@app.route("/analisar", methods=["POST"])
def analisar():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    texto_o = extrair_texto(pdf_o)
    texto_s = extrair_texto(pdf_s)

    # PEÇAS
    itens_o = extrair_itens(texto_o)
    itens_s = extrair_itens(texto_s)
    glosas, removidas = analisar_pecas(itens_o, itens_s)

    # SERVIÇOS (🔥 NOVO)
    serv_o = extrair_servicos(texto_o)
    serv_s = extrair_servicos(texto_s)
    divergencias_servicos = comparar_servicos(serv_o, serv_s)

    # MÃO DE OBRA REAL
    mao_o = extrair_mao_de_obra_total(texto_o)
    mao_s = extrair_mao_de_obra_total(texto_s)

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:red;">🔴 GLOSAS (PEÇAS)</h3>
    <ul>
    {% for g in glosas %}
        <li><b>{{g.descricao}}</b><br>
        Diferença: R$ {{g.diferenca}}</li><br>
    {% endfor %}
    </ul>

    <h3 style="color:blue;">🔵 GLOSAS (MÃO DE OBRA)</h3>
    <ul>
    {% for s in servicos %}
        <li><b>{{s.descricao}}</b><br>
        Diferença: R$ {{s.diferenca}}</li><br>
    {% endfor %}
    </ul>

    <h3 style="color:orange;">🟡 REMOVIDAS</h3>
    <ul>
    {% for r in removidas %}
        <li>{{r}}</li>
    {% endfor %}
    </ul>

    <h3 style="color:green;">💰 MÃO DE OBRA TOTAL</h3>
    <p>Oficina: R$ {{mao_o}}</p>
    <p>Seguradora: R$ {{mao_s}}</p>
    <p><b>Diferença: R$ {{mao_o - mao_s}}</b></p>

    <br><br>
    <a href="/">Voltar</a>
    """,
    glosas=glosas,
    removidas=removidas,
    servicos=divergencias_servicos,
    mao_o=mao_o,
    mao_s=mao_s
    )
