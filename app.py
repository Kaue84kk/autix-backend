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

# ---------------- LIMPEZA DESCRIÇÃO ----------------

def limpar_descricao(nome):
    nome = normalizar(nome)

    nome = re.sub(r"(R&I|R|P)\s*[\d,\.]+", "", nome)
    nome = re.sub(r"\b\d+\b", "", nome)
    nome = nome.replace("OFICINA", "").replace("SEGURADORA", "")
    nome = nome.strip()

    # remove lixo
    if nome in ["", "-", "--", "---"]:
        return None

    if len(nome) < 4:
        return None

    return nome

# ---------------- PALAVRA CHAVE ----------------

def palavra_chave(nome):
    palavras = nome.split()

    ignorar = {"DE", "DA", "DO", "TRAS", "ESQ", "DIR", "COMPONENTES"}

    palavras = [p for p in palavras if p not in ignorar]

    return palavras[0] if palavras else nome

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

        nome = limpar_descricao(linha_norm)

        if not nome:
            continue

        servicos.append({
            "descricao": nome,
            "chave": palavra_chave(nome),
            "ri": ri,
            "r": r,
            "p": p
        })

    return servicos

# ---------------- MATCH INTELIGENTE ----------------

def match_servico(s_o, lista):
    melhor = None
    score_max = 0

    for s in lista:
        score = 0

        if s_o["chave"] == s["chave"]:
            score += 2

        intersecao = len(set(s_o["descricao"].split()) & set(s["descricao"].split()))
        score += intersecao

        if score > score_max:
            score_max = score
            melhor = s

    if score_max >= 2:
        return melhor

    return None

# ---------------- COMPARAÇÃO ----------------

def comparar_servicos(serv_o, serv_s):
    removidos = []
    alterados = []
    substituidos = []
    usados_s = []

    for s_o in serv_o:
        match = match_servico(s_o, serv_s)

        if match:
            usados_s.append(match)

            if (
                s_o["ri"] != match["ri"] or
                s_o["r"] != match["r"] or
                s_o["p"] != match["p"]
            ):
                alterados.append({
                    "descricao": s_o["descricao"],
                    "oficina": s_o,
                    "seguradora": match,
                    "diff": {
                        "ri": round(match["ri"] - s_o["ri"], 2),
                        "r": round(match["r"] - s_o["r"], 2),
                        "p": round(match["p"] - s_o["p"], 2),
                    }
                })

        else:
            # tentativa de substituição (mesma chave)
            for s in serv_s:
                if s_o["chave"] == s["chave"]:
                    substituidos.append({
                        "oficina": s_o,
                        "seguradora": s
                    })
                    usados_s.append(s)
                    break
            else:
                removidos.append(s_o)

    novos = [s for s in serv_s if s not in usados_s]

    return removidos, alterados, substituidos, novos

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

    serv_o = extrair_servicos(texto_o)
    serv_s = extrair_servicos(texto_s)

    removidos, alterados, substituidos, novos = comparar_servicos(serv_o, serv_s)

    mao_o = extrair_mao_de_obra_total(texto_o)
    mao_s = extrair_mao_de_obra_total(texto_s)

    return render_template_string("""
    <h2>RESULTADO DA ANÁLISE</h2>

    <h3 style="color:blue;">🔵 SERVIÇOS ALTERADOS</h3>
    {% for a in alterados %}
        <p>
        <b>{{a.descricao}}</b><br>
        Oficina → R&I {{a.oficina.ri}} | R {{a.oficina.r}} | P {{a.oficina.p}}<br>
        Seguradora → R&I {{a.seguradora.ri}} | R {{a.seguradora.r}} | P {{a.seguradora.p}}<br>
        🔻 Corte → R&I {{a.diff.ri}} | R {{a.diff.r}} | P {{a.diff.p}}
        </p>
    {% endfor %}

    <h3 style="color:red;">🔴 REMOVIDOS</h3>
    {% for r in removidos %}
        <p>{{r.descricao}}</p>
    {% endfor %}

    <h3 style="color:purple;">🟣 SUBSTITUÍDOS</h3>
    {% for s in substituidos %}
        <p>
        Oficina: {{s.oficina.descricao}}<br>
        Seguradora: {{s.seguradora.descricao}}
        </p>
    {% endfor %}

    <h3 style="color:green;">🟢 NOVOS</h3>
    {% for n in novos %}
        <p>{{n.descricao}}</p>
    {% endfor %}

    <h3 style="color:green;">💰 MÃO DE OBRA TOTAL</h3>
    <p>Oficina: R$ {{mao_o}}</p>
    <p>Seguradora: R$ {{mao_s}}</p>
    <p><b>Diferença: R$ {{mao_o - mao_s}}</b></p>

    <br><br>
    <a href="/">Voltar</a>
    """,
    alterados=alterados,
    removidos=removidos,
    substituidos=substituidos,
    novos=novos,
    mao_o=mao_o,
    mao_s=mao_s
    )

if __name__ == "__main__":
    app.run(debug=True)
