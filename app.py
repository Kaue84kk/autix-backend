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

# ------------------ PEÇAS ------------------

def limpar_descricao(desc):
    desc = normalizar(desc)
    desc = re.sub(r"\b\d{5,}\b", "", desc)
    desc = desc.split("OFICINA")[0]
    desc = desc.split("SEGURADORA")[0]
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

def match_descricao(desc, lista):
    for item in lista:
        if desc[:25] in item["descricao"]:
            return item
    return None

def analisar_pecas(itens_o, itens_s):
    glosas = []
    removidas = []

    for item_o in itens_o:
        item_s = match_descricao(item_o["descricao"], itens_s)

        if not item_s:
            removidas.append(item_o["descricao"])
            continue

        if item_o["valor"] > item_s["valor"]:
            glosas.append({
                "descricao": item_o["descricao"],
                "diferenca": round(item_o["valor"] - item_s["valor"], 2)
            })

    return glosas, removidas

# ------------------ SERVIÇOS (MÃO DE OBRA) ------------------

def extrair_servicos(texto):
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
        nome = nome.replace("OFICINA", "").replace("SEGURADORA", "")
        nome = nome.strip()

        if len(nome) < 5:
            continue

        servicos.append({
            "descricao": nome,
            "ri": ri,
            "r": r,
            "p": p
        })

    return servicos

def comparar_servicos(serv_o, serv_s):
    removidos = []
    alterados = []

    for s_o in serv_o:
        match = None

        for s_s in serv_s:
            if s_o["descricao"][:30] in s_s["descricao"]:
                match = s_s
                break

        if not match:
            removidos.append(s_o)
            continue

        if (
            s_o["ri"] != match["ri"] or
            s_o["r"] != match["r"] or
            s_o["p"] != match["p"]
        ):
            alterados.append({
                "descricao": s_o["descricao"],
                "oficina": s_o,
                "seguradora": match
            })

    return removidos, alterados

# ------------------ MÃO DE OBRA TOTAL ------------------

def extrair_mao_de_obra_total(texto):
    match = re.search(r"MÃO DE OBRA.*R\$ ?([\d\.,]+)", texto.upper())
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

    # PEÇAS
    itens_o = extrair_itens(texto_o)
    itens_s = extrair_itens(texto_s)
    glosas, removidas_pecas = analisar_pecas(itens_o, itens_s)

    # SERVIÇOS
    serv_o = extrair_servicos(texto_o)
    serv_s = extrair_servicos(texto_s)
    removidos_serv, alterados_serv = comparar_servicos(serv_o, serv_s)

    # MÃO DE OBRA TOTAL
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

    <h3 style="color:orange;">🟡 PEÇAS REMOVIDAS</h3>
    <ul>
    {% for r in removidas_pecas %}
        <li>{{r}}</li>
    {% endfor %}
    </ul>

    <h3 style="color:red;">🔴 SERVIÇOS REMOVIDOS</h3>
    <ul>
    {% for r in removidos_serv %}
        <li><b>{{r.descricao}}</b></li>
    {% endfor %}
    </ul>

    <h3 style="color:blue;">🔵 SERVIÇOS ALTERADOS</h3>
    <ul>
    {% for a in alterados_serv %}
        <li>
        <b>{{a.descricao}}</b><br>
        Oficina: R&I {{a.oficina.ri}} | R {{a.oficina.r}} | P {{a.oficina.p}}<br>
        Seguradora: R&I {{a.seguradora.ri}} | R {{a.seguradora.r}} | P {{a.seguradora.p}}
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
    glosas=glosas,
    removidas_pecas=removidas_pecas,
    removidos_serv=removidos_serv,
    alterados_serv=alterados_serv,
    mao_o=mao_o,
    mao_s=mao_s
    )
    
if __name__ == "__main__":
    app.run(debug=True)
