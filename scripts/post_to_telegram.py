"""
PZ Ofertas — bot de postagem automática no Telegram (com marca d'água).

O que faz:
1. Lê products.json (catálogo atual do site).
2. Lê posted_ids.json (produtos que já foram postados no grupo).
3. Para cada produto novo:
   a. Baixa a foto do produto (campo "imagem").
   b. Cola o watermark.png (marca d'água fixa) no canto inferior direito da foto.
   c. Monta a copy no formato do plano da PZ (produto -> preço atual ->
      preço de referência -> cupom -> loja -> CTA -> observação).
   d. Envia a foto com marca d'água + a copy como legenda pro grupo/canal do Telegram.
   e. Se por algum motivo não conseguir baixar/marcar a foto, manda só o
      texto (fallback), pra nunca deixar de avisar por causa de uma imagem
      com problema.
4. Atualiza posted_ids.json com os novos IDs, pra não postar de novo.

Roda sozinho pelo GitHub Actions (.github/workflows/telegram-post.yml)
toda vez que o products.json é alterado.

Dependências: requests, Pillow (instaladas pelo workflow via pip).
"""

import json
import os
import sys
from io import BytesIO

import requests
from PIL import Image

PRODUCTS_FILE = "products.json"
POSTED_FILE = "posted_ids.json"
WATERMARK_FILE = "watermark.png"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PZOfertasBot/1.0)"}


def formatar_preco(v):
    if v is None:
        return None
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_copy(produto):
    nome = produto["nome"]
    loja = produto["loja"]
    preco = formatar_preco(produto.get("preco"))
    preco_ref = formatar_preco(produto.get("precoRef"))
    cupom = produto.get("cupom")
    url = produto.get("url", "#")

    linhas = [f"🔥 *{nome}*", ""]

    if preco_ref:
        linhas.append(f"De ~{preco_ref}~ por *{preco}*")
    else:
        linhas.append(f"Por *{preco}*")

    if cupom:
        linhas.append(f"🏷️ Cupom: `{cupom}`")

    linhas.append(f"🛒 Loja: {loja}")
    linhas.append(f"👉 [Ver oferta]({url})")
    linhas.append("")
    linhas.append("_Preço e estoque podem mudar a qualquer momento — confirme antes de finalizar a compra._")

    return "\n".join(linhas)


def gerar_imagem_com_marca_dagua(url_imagem):
    """Baixa a foto do produto e cola o watermark.png no canto inferior direito.
    Devolve os bytes da imagem final (JPEG) ou None se algo falhar."""
    if not os.path.exists(WATERMARK_FILE):
        print(f"{WATERMARK_FILE} não encontrado, pulando marca d'água.")
        return None

    try:
        resp = requests.get(url_imagem, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        foto = Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        print("Não consegui baixar a imagem do produto:", e)
        return None

    try:
        marca = Image.open(WATERMARK_FILE).convert("RGBA")

        # marca d'água proporcional: ~28% da largura da foto
        alvo_largura = int(foto.width * 0.28)
        proporcao = alvo_largura / marca.width
        marca = marca.resize((alvo_largura, int(marca.height * proporcao)), Image.LANCZOS)

        margem = int(foto.width * 0.04)
        posicao = (foto.width - marca.width - margem, foto.height - marca.height - margem)

        foto.paste(marca, posicao, marca)

        saida = BytesIO()
        foto.convert("RGB").save(saida, format="JPEG", quality=88)
        return saida.getvalue()
    except Exception as e:
        print("Erro ao aplicar a marca d'água:", e)
        return None


def enviar_foto_telegram(imagem_bytes, legenda):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    files = {"photo": ("oferta.jpg", imagem_bytes, "image/jpeg")}
    data = {"chat_id": CHAT_ID, "caption": legenda, "parse_mode": "Markdown"}
    try:
        r = requests.post(api_url, data=data, files=files, timeout=30)
        print("Telegram (foto):", r.status_code, r.text[:200])
        return r.ok
    except Exception as e:
        print("Erro ao enviar foto pro Telegram:", e)
        return False


def enviar_texto_telegram(texto):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": texto,
        "parse_mode": "Markdown",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(api_url, data=data, timeout=20)
        print("Telegram (texto):", r.status_code, r.text[:200])
        return r.ok
    except Exception as e:
        print("Erro ao enviar texto pro Telegram:", e)
        return False


def postar_produto(produto):
    copy = montar_copy(produto)
    imagem_url = produto.get("imagem")

    if imagem_url:
        imagem_final = gerar_imagem_com_marca_dagua(imagem_url)
        if imagem_final:
            if enviar_foto_telegram(imagem_final, copy):
                return True
            print("Falha ao enviar como foto, tentando como texto...")

    # fallback: manda só o texto se a imagem falhar por qualquer motivo
    return enviar_texto_telegram(copy)


def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID não configurados. Encerrando sem postar.")
        return

    if not os.path.exists(PRODUCTS_FILE):
        print(f"{PRODUCTS_FILE} não encontrado.")
        sys.exit(1)

    with open(PRODUCTS_FILE, encoding="utf-8") as f:
        produtos = json.load(f)

    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, encoding="utf-8") as f:
            postados = set(json.load(f))
    else:
        postados = set()

    novos = [p for p in produtos if p["id"] not in postados]

    if not novos:
        print("Nenhum produto novo pra postar.")
        return

    for produto in novos:
        ok = postar_produto(produto)
        if ok:
            postados.add(produto["id"])

    with open(POSTED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(postados), f)

    print(f"{len(novos)} produto(s) processado(s).")


if __name__ == "__main__":
    main()
