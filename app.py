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
# LIMPEZA INTELIGENTE (V6 BASE)
# =========================
def linha_valida(linha):

    # ignora linhas vazias
    if not linha.strip():
        return False

    # ignora resumos financeiros
    if "Total" in linha or "Bruto" in linha or "Líquido" in linha:
        return False

    # ignora linhas gigantes com vários valores
    if len(re.findall(r'\d+[.,]\d{2}', linha)) > 3:
        return False

    # ignora porcentagem
    if "%" in linha:
        return False

    return True


# =========================
# EXTRAIR ITENS
# =========================
def extrair_itens(texto):
    itens = []
    linhas = texto.split("\n")

    for linha in linhas:

        if not linha_valida(linha):
            continue

        # ignora R&I (operação)
        if "R&I" in linha:
            continue

        try:
            match = re.search(r'(\d+[.,]\d{2})', linha)
            if not match:
                continue

            valor = float(match.group(1).replace(".", "").replace(",", "."))

            codigo_match = re.search(r'\b\d{6,}\b', linha)
            codigo = codigo_match.group(0) if codigo_match else linha[:40]

            # limpa descrição
            descricao = re.sub(r'\d+[.,]\d{2}', '', linha)
            descricao = re.sub(r'[^\w\s/.-]', '', descricao).strip()

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

    for item_of in oficina:
        encontrado = False

        for item_seg in seguradora:
            if item_of["codigo"] == item_seg["codigo"]:
                encontrado = True

                if abs(item_of["valor"] - item_seg["valor"]) > 0.01:
                    divergencias.append({
                        "tipo": "VALOR_DIFERENTE",
                        "descricao": item_of["descricao"],
                        "oficina": item_of["valor"],
                        "seguradora": item_seg["valor"]
                    })

        if not encontrado:
            divergencias.append({
                "tipo": "NAO_ENCONTRADO",
                "descricao": item_of["descricao"],
                "oficina": item_of["valor"]
            })

    return divergencias


# =========================
# FORMATAR SAÍDA PROFISSIONAL
# =========================
def formatar_saida(divergencias):
    resultado = []

    for d in divergencias:

        if d["tipo"] == "VALOR_DIFERENTE":
            diferenca = d["oficina"] - d["seguradora"]

            resultado.append({
                "tipo": "DIVERGENCIA_DE_VALOR",
                "descricao": d["descricao"],
                "oficina": f"R$ {d['oficina']:.2f}",
                "seguradora": f"R$ {d['seguradora']:.2f}",
                "diferenca": f"R$ {diferenca:.2f}",
                "acao": "NEGOCIAR DIFERENCA"
            })

        elif d["tipo"] == "NAO_ENCONTRADO":
            resultado.append({
                "tipo": "ITEM_NAO_APROVADO",
                "descricao": d["descricao"],
                "oficina": f"R$ {d['oficina']:.2f}",
                "acao": "VALIDAR COM SEGURADORA"
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

    resultado_final = formatar_saida(divergencias)

    return {"analise": resultado_final}
