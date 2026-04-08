from fastapi import FastAPI, UploadFile, File
import pdfplumber

app = FastAPI()

def extrair_texto_pdf(file):
    texto = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            texto += page.extract_text() + "\n"
    return texto

def extrair_itens(texto):
    itens = []

    linhas = texto.split("\n")

    for linha in linhas:
        if "R$" in linha:

            try:
                descricao = linha

                valor = None
                match = re.search(r'R\$\s*([\d,.]+)', linha)
                if match:
                    valor = float(match.group(1).replace(".", "").replace(",", "."))

                itens.append({
                    "descricao": descricao,
                    "valor": valor
                })

            except:
                continue

    return itens

def comparar(oficina, seguradora):
    divergencias = []

    for item_of in oficina:
        encontrou = False

        for item_seg in seguradora:

            if item_of["descricao"][:50] == item_seg["descricao"][:50]:
                encontrou = True

                if item_of["valor"] != item_seg["valor"]:
                    divergencias.append({
                        "tipo": "VALOR_DIFERENTE",
                        "descricao": item_of["descricao"],
                        "valor_oficina": item_of["valor"],
                        "valor_seguradora": item_seg["valor"],
                        "diferenca": round(item_of["valor"] - item_seg["valor"], 2)
                    })

        if not encontrou:
            divergencias.append({
                "tipo": "NAO_ENCONTRADO",
                "descricao": item_of["descricao"],
                "valor_oficina": item_of["valor"]
            })

    return divergencias

@app.post("/analisar")
async def analisar(
    pdf_oficina: UploadFile = File(...),
    pdf_seguradora: UploadFile = File(...)
):
    texto_oficina = extrair_texto_pdf(pdf_oficina.file)
    texto_seguradora = extrair_texto_pdf(pdf_seguradora.file)

    itens_of = extrair_itens(texto_oficina)
    itens_seg = extrair_itens(texto_seguradora)

    divergencias = comparar(itens_of, itens_seg)

    return {
        "divergencias": divergencias
    }
