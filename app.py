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

def normalizar(txt):
    return re.sub(r'\s+', ' ', txt.upper()).strip()

def limpar_valor(valor):
    try:
        return float(valor.replace("R$", "").replace(".", "").replace(",", "."))
    except:
        return 0.0

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

# ---------------- PEÇAS ----------------

def extrair_pecas(texto):
    pecas = []

    for linha in texto.split("\n"):
        linha_norm = normalizar(linha)

        if "R$" in linha_norm and re.search(r"\d{5,}", linha_norm):

            valor = limpar_valor(linha_norm.split("R$")[-1])

            desc = linha_norm
            desc = re.sub(r"\b\d{5,}\b", "", desc)
            desc = desc.split("R$")[0]
            desc = desc.split("OFICINA")[0]
            desc = desc.split("SEGURADORA")[0]
            desc = desc.strip()

            pecas.append({
                "descricao": desc,
                "valor": valor
            })

    return pecas

def comparar_pecas(p_o, p_s):
    glosas = []
    removidas = []

    for po in p_o:
        match = None

        for ps in p_s:
            if po["descricao"][:25] in ps["descricao"]:
                match = ps
                break

        if not match:
            removidas.append(po)
        else:
            if po["valor"] > match["valor"]:
                glosas.append({
                    "descricao": po["descricao"],
                    "oficina": po["valor"],
                    "seguradora": match["valor"],
                    "diferenca": round(po["valor"] - match["valor"], 2)
                })

    return glosas, removidas

# ---------------- SERVIÇOS ----------------

def extrair_servicos(texto):
    servicos = []

    for linha in texto.split("\n"):
        linha_norm = normalizar(linha)

        if not linha_norm.startswith(("R&I", "R ", "P ")):
            continue

        ri = re.search(r"R&I\s*([\d,\.]+)", linha_norm)
        r = re.search(r"\bR\s*([\d,\.]+)", linha_norm)
        p = re.search(r"\bP\s*([\d,\.]+)", linha_norm)

        ri = float(ri.group(1).replace(",", ".")) if ri else 0
        r = float(r.group(1).replace(",", ".")) if r else 0
        p = float(p.group(1).replace(",", ".")) if p else 0

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

def similaridade(a, b):
    a_set = set(a.split())
    b_set = set(b.split())
    return len(a_set & b_set) / max(len(a_set), 1)

def comparar_servicos(serv_o, serv_s):
    removidos = []
    alterados = []
    substituidos = []
    usados_s = []

    for s_o in serv_o:
        melhor = None
        score_max = 0

        for s_s in serv_s:
            score = similaridade(s_o["descricao"], s_s["descricao"])
            if score > score_max:
                score_max = score
                melhor = s_s

        if melhor and score_max > 0.6:
            usados_s.append(melhor)

            if (
                s_o["ri"] != melhor["ri"] or
                s_o["r"] != melhor["r"] or
                s_o["p"] != melhor["p"]
            ):
                alterados.append({
                    "descricao": s_o["descricao"],
                    "oficina": s_o,
                    "seguradora": melhor,
                    "diff": {
                        "ri": round(melhor["ri"] - s_o["ri"], 2),
                        "r": round(melhor["r"] - s_o["r"], 2),
                        "p": round(melhor["p"] - s_o["p"], 2),
                    }
                })
        else:
            removidos.append(s_o)

    novos = [s for s in serv_s if s not in usados_s]

    return removidos, alterados, novos

# ---------------- MÃO DE OBRA TOTAL ----------------

def extrair_mao_de_obra_total(texto):
    match = re.search(r"MÃO DE OBRA.*R\$ ?([\d\.,]+)", texto.upper())
    if match:
        return limpar_valor(match.group(1))
    return 0.0

# ---------------- ROUTE ----------------

@app.route("/analisar", methods=["POST"])
def analisar():
    pdf_o = request.files["oficina"]
    pdf_s = request.files["seguradora"]

    texto_o = extrair_texto(pdf_o)
    texto_s = extrair_texto(pdf_s)

    # PEÇAS
    pecas_o = extrair_pecas(texto_o)
    pecas_s = extrair_pecas(texto_s)
    glosas_pecas, removidas_pecas = comparar_pecas(pecas_o, pecas_s)

    # SERVIÇOS
    serv_o = extrair_servicos(texto_o)
    serv_s = extrair_servicos(texto_s)
    removidos_serv, alterados_serv, novos_serv = comparar_servicos(serv_o, serv_s)

    # TOTAL
    mao_o = extrair_mao_de_obra_total(texto_o)
    mao_s = extrair_mao_de_obra_total(texto_s)

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:red;">🔴 GLOSAS (PEÇAS)</h3>
    {% for g in glosas_pecas %}
        <p><b>{{g.descricao}}</b><br>
        Oficina: R$ {{g.oficina}}<br>
        Seguradora: R$ {{g.seguradora}}<br>
        Diferença: <b>R$ {{g.diferenca}}</b></p>
    {% endfor %}

    <h3 style="color:orange;">🟡 PEÇAS REMOVIDAS</h3>
    {% for r in removidas_pecas %}
        <p>{{r.descricao}}</p>
    {% endfor %}

    <h3 style="color:blue;">🔵 SERVIÇOS ALTERADOS</h3>
    {% for a in alterados_serv %}
        <p>
        <b>{{a.descricao}}</b><br>
        Oficina → R&I {{a.oficina.ri}} | R {{a.oficina.r}} | P {{a.oficina.p}}<br>
        Seguradora → R&I {{a.seguradora.ri}} | R {{a.seguradora.r}} | P {{a.seguradora.p}}<br>
        🔻 Corte → R&I {{a.diff.ri}} | R {{a.diff.r}} | P {{a.diff.p}}
        </p>
    {% endfor %}

    <h3 style="color:red;">🔴 SERVIÇOS REMOVIDOS</h3>
    {% for r in removidos_serv %}
        <p><b>{{r.descricao}}</b></p>
    {% endfor %}

    <h3 style="color:green;">🟢 NOVOS (SEGURADORA)</h3>
    {% for n in novos_serv %}
        <p>{{n.descricao}}</p>
    {% endfor %}

    <h3 style="color:green;">💰 MÃO DE OBRA TOTAL</h3>
    <p>Oficina: R$ {{mao_o}}</p>
    <p>Seguradora: R$ {{mao_s}}</p>
    <p><b>Diferença: R$ {{mao_o - mao_s}}</b></p>

    <br><br>
    <a href="/">Voltar</a>
    """,
    glosas_pecas=glosas_pecas,
    removidas_pecas=removidas_pecas,
    alterados_serv=alterados_serv,
    removidos_serv=removidos_serv,
    novos_serv=novos_serv,
    mao_o=mao_o,
    mao_s=mao_s
    )

if __name__ == "__main__":
    app.run(debug=True)
