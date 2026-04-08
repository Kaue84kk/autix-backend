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
        if "R$" in linha and ("Seguradora" in linha or "Oficina" in linha):
            try:
                valor = None
                partes = linha.split()

                for i, p in enumerate(partes):
                    if p == "R$":
                        valor = float(partes[i+1].replace(",", "."))

                itens.append({
                    "linha": linha,
                    "valor": valor
                })
            except:
                pass

    return itens

def comparar(oficina, seguradora):
    divergencias = []

    for item_of in oficina:
        encontrou = False

        for item_seg in seguradora:
            if item_of["linha"][:40] == item_seg["linha"][:40]:
                encontrou = True

                if item_of["valor"] != item_seg["valor"]:
                    divergencias.append({
                        "tipo": "VALOR_DIFERENTE",
                        "oficina": item_of["linha"],
                        "seguradora": item_seg["linha"]
                    })

        if not encontrou:
            divergencias.append({
                "tipo": "NAO_ENCONTRADO",
                "oficina": item_of["linha"]
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
