from fastapi import FastAPI, UploadFile, File
import pdfplumber
import re

app = FastAPI()

# =========================
# EXTRAIR TEXTO
# =========================
def extrair_texto_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
    return texto


# =========================
# IDENTIFICAR LINHA DE PEÇA REAL
# =========================
def linha_valida(linha):

    if not linha.strip():
        return False

    # precisa ter código grande
    if not re.search(r'\b\d{6,}\b', linha):
        return False

    # precisa ter valor monetário
    if not re.search(r'R\$\s*\d', linha):
        return False

    # ignora resumo
    if any(x in linha for x in ["Total", "Bruto", "Líquido", "%"]):
        return False

    return True


# =========================
# EXTRAIR ITENS (VERSÃO LIMPA)
# =========================
def extrair_itens(texto):
    itens = []
    linhas = texto.split("\n")

    for linha in linhas:

        if not linha_valida(linha):
            continue

        try:
            # código
            codigo = re.search(r'\b\d{6,}\b', linha).group()

            # valor (último valor da linha)
            valores = re.findall(r'R\$\s*([\d.,]+)', linha)
            if not valores:
                continue

            valor = float(valores[-1].replace(".", "").replace(",", "."))

            # descrição limpa
            descricao = linha

            # remove código
            descricao = re.sub(r'\b\d{6,}\b', '', descricao)

            # remove valores
            descricao = re.sub(r'R\$\s*[\d.,]+', '', descricao)

            # remove ruídos
            descricao = re.sub(r'[TPR\-]+', '', descricao)

            descricao = re.sub(r'\s+', ' ', descricao).strip()

            itens.append({
                "codigo": codigo,
                "descricao": descricao,
                "valor": valor
            })

        except:
            continue

    return itens


# =========================
# COMPARAÇÃO INTELIGENTE
# =========================
def comparar(oficina, seguradora):
    divergencias = []

    mapa_seg = {item["codigo"]: item for item in seguradora}

    for item_of in oficina:

        item_seg = mapa_seg.get(item_of["codigo"])

        if item_seg:
            if abs(item_of["valor"] - item_seg["valor"]) > 0.01:
                divergencias.append({
                    "tipo": "VALOR_DIFERENTE",
                    "descricao": item_of["descricao"],
                    "oficina": item_of["valor"],
                    "seguradora": item_seg["valor"]
                })
        else:
            divergencias.append({
                "tipo": "NAO_ENCONTRADO",
                "descricao": item_of["descricao"],
                "oficina": item_of["valor"]
            })

    return divergencias


# =========================
# FORMATAÇÃO PROFISSIONAL
# =========================
def formatar_saida(divergencias):
    resultado = []

    for d in divergencias:

        if d["tipo"] == "VALOR_DIFERENTE":
            diff = d["oficina"] - d["seguradora"]

            resultado.append({
                "tipo": "DIVERGENCIA_DE_VALOR",
                "item": d["descricao"],
                "oficina": f"R$ {d['oficina']:.2f}",
                "seguradora": f"R$ {d['seguradora']:.2f}",
                "diferenca": f"R$ {diff:.2f}",
                "acao": "NEGOCIAR"
            })

        else:
            resultado.append({
                "tipo": "ITEM_NAO_APROVADO",
                "item": d["descricao"],
                "oficina": f"R$ {d['oficina']:.2f}",
                "acao": "COBRAR SEGURADORA"
            })

    return resultado


# =========================
# ENDPOINT
# =========================
@app.post("/analisar")
async def analisar(
    pdf_oficina: UploadFile = File(...),
    pdf_seguradora: UploadFile = File(...)
):
    texto_oficina = extrair_texto_pdf(pdf_oficina.file)
    texto_seguradora = extrair_texto_pdf(pdf_seguradora.file)

    itens_oficina = extrair_itens(texto_oficina)
    itens_seguradora = extrair_itens(texto_seguradora)

    divergencias = comparar(itens_oficina, itens_seguradora)

    return {
        "resumo": {
            "total_itens_oficina": len(itens_oficina),
            "total_itens_seguradora": len(itens_seguradora),
            "divergencias": len(divergencias)
        },
        "analise": formatar_saida(divergencias)
    }
