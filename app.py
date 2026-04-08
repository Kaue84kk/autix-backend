from fastapi import FastAPI, UploadFile, File
import pdfplumber
import re

app = FastAPI()

def extrair_texto_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() or ""
    return texto

def extrair_itens(texto):
    itens = []
    linhas = texto.split("\n")

    for linha in linhas:
        if not any(char.isdigit() for char in linha):
            continue

        try:
            match = re.search(r'(\d+[.,]\d{2})', linha)
            if not match:
                continue

            valor = float(match.group(1).replace(".", "").replace(",", "."))

            codigo_match = re.search(r'\b\d{6,}\b', linha)
            codigo = codigo_match.group(0) if codigo_match else linha

            itens.append({
                "codigo": codigo,
                "descricao": linha.strip(),
                "valor": valor
            })

        except:
            continue

    return itens

def comparar(oficina, seguradora):
    divergencias = []

    for item_of in oficina:
        encontrado = False

        for item_seg in seguradora:
            if item_of["codigo"] == item_seg["codigo"]:
                encontrado = True

                if item_of["valor"] != item_seg["valor"]:
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

    return {"divergencias": divergencias}
