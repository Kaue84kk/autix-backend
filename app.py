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

# ---------------- HELPERS ----------------

def limpar_valor(v):
    try:
        return float(v.replace("R$", "").replace(".", "").replace(",", "."))
    except:
        return 0.0

def normalizar(txt):
    return re.sub(r'\s+', ' ', str(txt).upper()).strip()

# ---------------- EXTRAÇÃO POR TABELA ----------------

def extrair_tabela(pdf_file):
    dados = []

    pdf_bytes = pdf_file.read()
    pdf_stream = io.BytesIO(pdf_bytes)

    with pdfplumber.open(pdf_stream) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                for row in table:
                    if not row:
                        continue

                    linha = [normalizar(c) for c in row if c]

                    if len(linha) < 3:
                        continue

                    texto = " ".join(linha)

                    # identificar tipo
                    tipo = None
                    if "R&I" in texto:
                        tipo = "RI"
                    elif re.search(r"\bR\b", texto):
                        tipo = "R"
                    elif re.search(r"\bP\b", texto):
                        tipo = "P"

                    # valor
                    valor = 0
                    for c in linha:
                        if "R$" in c:
                            valor = limpar_valor(c)

                    # descrição
                    desc = texto
                    desc = re.sub(r"R&I|R|P", "", desc)
                    desc = re.sub(r"\d+[,\.]\d+", "", desc)
                    desc = re.sub(r"\b\d+\b", "", desc)
                    desc = desc.replace("R$", "").strip()

                    if len(desc) < 5:
                        continue

                    dados.append({
                        "tipo": tipo,
                        "descricao": desc,
                        "valor": valor
                    })

    return dados

# ---------------- COMPARAÇÃO ----------------

def comparar(lista_o, lista_s):
    glosas = []
    removidos = []
    novos = []

    for o in lista_o:
        match = None

        for s in lista_s:
            if o["descricao"][:30] in s["descricao"]:
                match = s
                break

        if not match:
            removidos.append(o)
        else:
            if o["valor"] > match["valor"]:
                glosas.append({
                    "descricao": o["descricao"],
                    "oficina": o["valor"],
                    "seguradora": match["valor"],
                    "diff": round(o["valor"] - match["valor"], 2)
                })

    for s in lista_s:
        if not any(s["descricao"][:30] in o["descricao"] for o in lista_o):
            novos.append(s)

    return glosas, removidos, novos

# ---------------- TOTAL ----------------

def extrair_total(texto):
    match = re.search(r"MÃO DE OBRA.*R\$ ?([\d\.,]+)", texto.upper())
    if match:
        return limpar_valor(match.group(1))
    return 0.0

def extrair_texto(pdf_file):
    texto = ""
    pdf_file.seek(0)
    with pdfplumber.open(pdf_file) as pdf:
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                texto += t
    return texto

# ---------------- ROUTE ----------------

@app.route("/analisar", methods=["POST"])
def analisar():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    dados_o = extrair_tabela(pdf_o)
    pdf_s.seek(0)
    dados_s = extrair_tabela(pdf_s)

    glosas, removidos, novos = comparar(dados_o, dados_s)

    pdf_o.seek(0)
    pdf_s.seek(0)

    mao_o = extrair_total(extrair_texto(pdf_o))
    mao_s = extrair_total(extrair_texto(pdf_s))

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:red;">🔴 GLOSAS</h3>
    {% for g in glosas %}
        <p><b>{{g.descricao}}</b><br>
        Oficina: R$ {{g.oficina}}<br>
        Seguradora: R$ {{g.seguradora}}<br>
        Diferença: R$ {{g.diff}}</p>
    {% endfor %}

    <h3 style="color:orange;">🟡 REMOVIDOS</h3>
    {% for r in removidos %}
        <p>{{r.descricao}}</p>
    {% endfor %}

    <h3 style="color:green;">🟢 NOVOS</h3>
    {% for n in novos %}
        <p>{{n.descricao}}</p>
    {% endfor %}

    <h3 style="color:green;">💰 MÃO DE OBRA TOTAL</h3>
    <p>Oficina: R$ {{mao_o}}</p>
    <p>Seguradora: R$ {{mao_s}}</p>
    <p><b>Diferença: R$ {{mao_o - mao_s}}</b></p>
    """,
    glosas=glosas,
    removidos=removidos,
    novos=novos,
    mao_o=mao_o,
    mao_s=mao_s
    )

if __name__ == "__main__":
    app.run(debug=True)
