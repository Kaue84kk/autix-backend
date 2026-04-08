from fastapi import FastAPI, UploadFile, File
import fitz
from openai import OpenAI
import os

app = FastAPI()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extrair_texto_pdf(file_bytes):
    texto = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            texto += page.get_text()
    return texto


@app.post("/analisar")
async def analisar(
    pdf_oficina: UploadFile = File(...),
    pdf_seguradora: UploadFile = File(...)
):

    oficina_bytes = await pdf_oficina.read()
    seguradora_bytes = await pdf_seguradora.read()

    texto_oficina = extrair_texto_pdf(oficina_bytes)
    texto_seguradora = extrair_texto_pdf(seguradora_bytes)

    prompt = f"""
Você é um especialista em auditoria de orçamentos automotivos de seguradoras.

Sua função NÃO é apenas comparar valores.

Seu objetivo é identificar EXCLUSIVAMENTE o que exige AÇÃO da oficina.

---

REGRA MESTRA:

A análise deve mostrar apenas:

- O que a oficina PRECISA agir
- O que foi ALTERADO de forma relevante
- O que pode gerar prejuízo ou retrabalho

---

BASE FINANCEIRA:

Se existir "LÍQUIDO GERAL":
usar como base oficial
senão:
usar TOTAL GERAL

---

LEITURA DO DOCUMENTO:

Considerar apenas:

- PEÇAS - TROCA
- PEÇAS - RECUPERAR
- MONTAGEM / DESMONTAGEM
- SERVIÇOS

Ignorar completamente:

- LISTA DE PEÇAS FORNECIDAS
- STATUS DE ENTREGA

---

ETAPA 1 — EXTRAÇÃO

Extrair:
- peças
- mão de obra (R&I, R, P)
- serviços

---

ETAPA 2 — MATCH

Comparar por:
1. Código
2. Similaridade

---

ETAPA 3 — DETECÇÃO

MÃO DE OBRA:

Para cada item:

Se horas_seguradora < horas_oficina:
→ glosa_mao_de_obra_item

Se horas_seguradora > horas_oficina:
→ aumento_mao_de_obra_item

Analisar separadamente:
- R&I
- R
- P

---

PEÇAS:

Se fornecimento mudou:
→ mudanca_fornecimento

Se valor seguradora < valor oficina:
→ glosa_valor_peca_oficina

---

PEÇAS REMOVIDAS:

Se item existe na oficina e não existe na seguradora:
→ peça removida

---

ETAPA 4 — RESULTADO

Calcular diferença e classificar:
- prejuizo_real
- ganho_real
- neutro

---

FORMATO DE SAÍDA:

🔴 CORTES DE MÃO DE OBRA
- descricao
- tipo
- horas_oficina
- horas_seguradora
- diferenca

🔵 IMPACTOS EM PEÇAS
- descricao
- tipo
- valores

🟡 ALERTAS OPERACIONAIS

💰 RESULTADO FINAL

---

ORÇAMENTO OFICINA:
{texto_oficina}

---

ORÇAMENTO SEGURADORA:
{texto_seguradora}
"""

    resposta = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    return {"analise": resposta.choices[0].message.content}
