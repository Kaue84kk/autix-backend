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

# ------------------ HELPERS ------------------

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

# ------------------ VALORES HORA ------------------

def extrair_valores_hora(texto):
    mao = re.search(r"MÃO DE OBRA\s*R\$ ?([\d\.,]+)", texto.upper())
    rep = re.search(r"REPARAÇÃO\s*R\$ ?([\d\.,]+)", texto.upper())
    pin = re.search(r"PINTURA.*R\$ ?([\d\.,]+)", texto.upper())

    return {
        "mao": limpar_valor(mao.group(1)) if mao else 0,
        "rep": limpar_valor(rep.group(1)) if rep else 0,
        "pin": limpar_valor(pin.group(1)) if pin else 0
    }

# ------------------ SERVIÇOS ------------------

def extrair_servicos(texto, valores_hora):
    servicos = []

    for linha in texto.split("\n"):
        linha_norm = normalizar(linha)

        if not linha_norm.startswith(("R&I", "R ", "P ")):
            continue

        # extrair horas
        ri = re.search(r"R&I\s*([\d,\.]+)", linha_norm)
        r = re.search(r"\bR\s*([\d,\.]+)", linha_norm)
        p = re.search(r"\bP\s*([\d,\.]+)", linha_norm)

        ri = float(ri.group(1).replace(",", ".")) if ri else 0
        r = float(r.group(1).replace(",", ".")) if r else 0
        p = float(p.group(1).replace(",", ".")) if p else 0

        # limpar descrição
        nome = re.sub(r"(R&I|R|P)\s*[\d,\.]+", "", linha_norm)
        nome = re.sub(r"\b\d+\b", "", nome)
        nome = nome.replace("OFICINA", "").strip()

        if len(nome) < 5:
            continue

        valor_total = (
            ri * valores_hora["mao"] +
            r * valores_hora["rep"] +
            p * valores_hora["pin"]
        )

        servicos.append({
            "descricao": nome,
            "valor": round(valor_total, 2)
        })

    return servicos

# ------------------ MATCH INTELIGENTE ------------------

def similaridade(a, b):
    a = set(a.split())
    b = set(b.split())
    return len(a & b) / max(len(a), 1)

def encontrar_match(serv, lista):
    melhor = None
    score_max = 0

    for s in lista:
        score = similaridade(serv["descricao"], s["descricao"])
        if score > score_max:
            score_max = score
            melhor = s

    if score_max > 0.5:
        return melhor

    return None

# ------------------ COMPARAÇÃO ------------------

def comparar_servicos(serv_o, serv_s):
    divergencias = []

    for s_o in serv_o:
        s_s = encontrar_match(s_o, serv_s)

        if not s_s:
            continue

        if s_o["valor"] > s_s["valor"]:
            divergencias.append({
                "descricao": s_o["descricao"],
                "oficina": s_o["valor"],
                "seguradora": s_s["valor"],
                "diferenca": round(s_o["valor"] - s_s["valor"], 2)
            })

    return divergencias

# ------------------ MÃO DE OBRA TOTAL ------------------

def extrair_mao_de_obra_total(texto):
    match = re.search(r"L[ÍI]QUIDO DE MÃO DE OBRA\s*\+\s*R\$ ?([\d\.,]+)", texto.upper())
    if match:
        return limpar_valor(match.group(1))
    return 0.0

# ------------------ ROUTE ------------------

@app.route("/analisar", methods=["POST"])
def analisar():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    texto_o = extrair_texto(pdf_o)
    texto_s = extrair_texto(pdf_s)

    valores_o = extrair_valores_hora(texto_o)
    valores_s = extrair_valores_hora(texto_s)

    serv_o = extrair_servicos(texto_o, valores_o)
    serv_s = extrair_servicos(texto_s, valores_s)

    divergencias = comparar_servicos(serv_o, serv_s)

    mao_o = extrair_mao_de_obra_total(texto_o)
    mao_s = extrair_mao_de_obra_total(texto_s)

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:blue;">🔵 GLOSAS (MÃO DE OBRA)</h3>
    <ul>
    {% for s in servicos %}
        <li>
        <b>{{s.descricao}}</b><br>
        Oficina: R$ {{s.oficina}}<br>
        Seguradora: R$ {{s.seguradora}}<br>
        Diferença: <b style="color:red;">R$ {{s.diferenca}}</b>
        </li><br>
    {% endfor %}
    </ul>

    <h3 style="color:green;">💰 MÃO DE OBRA TOTAL</h3>
    <p>Oficina: R$ {{mao_o}}</p>
    <p>Seguradora: R$ {{mao_s}}</p>
    <p><b>Diferença: R$ {{mao_o - mao_s}}</b></p>

    <br><br>
    <a href="/">Voltar</a>
    """,
    servicos=divergencias,
    mao_o=mao_o,
    mao_s=mao_s
    )
