"""Constroi o indice FAISS a partir dos documentos de `data/documentos/`.

Rode uma vez antes de subir o agente, e de novo sempre que os documentos
mudarem:

    uv run python scripts/ingerir_documentos.py

O indice gerado fica em `data/faiss_index/` e nao vai pro git (ver
`.gitignore`): e um artefato derivado, especifico do modelo de embeddings
que o gerou, e reconstruivel em segundos por quem clonar o repositorio.

Este script e um utilitario de operacao, nao parte do agente — ele nao e
importado por `core/` nem por `main.py`. Toda a logica de FAISS que ele usa
mora no adapter (`construir_indice`), pra que o que a ingestao produz seja
exatamente o que a busca consome.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.knowledge.faiss_repository import (  # noqa: E402
    MODELO_EMBEDDINGS_PADRAO,
    construir_indice,
)

RAIZ = Path(__file__).resolve().parent.parent
PASTA_DOCUMENTOS = RAIZ / "data" / "documentos"
PASTA_INDICE = RAIZ / "data" / "faiss_index"

SEPARADOR_DE_TRECHOS = "\n\n"
"""Um trecho por paragrafo.

Chunking sofisticado (janela deslizante, sobreposicao, split por tokens)
nao se paga com um acervo deste tamanho, e atrapalharia a leitura dos
scores na calibragem do limiar. Se o acervo crescer, este e o primeiro
lugar a revisitar.
"""


def carregar_trechos(pasta: Path) -> list[str]:
    """Le os .md da pasta e quebra cada um em paragrafos nao vazios."""
    trechos: list[str] = []
    for arquivo in sorted(pasta.glob("*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        for bloco in texto.split(SEPARADOR_DE_TRECHOS):
            limpo = " ".join(bloco.split())
            if limpo and not limpo.startswith("#"):
                trechos.append(limpo)
    return trechos


def main() -> int:
    if not PASTA_DOCUMENTOS.is_dir():
        print(f"pasta de documentos nao encontrada: {PASTA_DOCUMENTOS}")
        return 1

    trechos = carregar_trechos(PASTA_DOCUMENTOS)
    if not trechos:
        print(f"nenhum trecho encontrado em {PASTA_DOCUMENTOS}/*.md")
        return 1

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    modelo = os.environ.get("OLLAMA_EMBEDDINGS_MODEL", MODELO_EMBEDDINGS_PADRAO)

    print(f"{len(trechos)} trechos lidos de {PASTA_DOCUMENTOS}")
    print(f"gerando embeddings com {modelo} em {base_url}...")
    construir_indice(
        trechos,
        caminho_destino=PASTA_INDICE,
        base_url=base_url,
        modelo_embeddings=modelo,
    )
    print(f"indice salvo em {PASTA_INDICE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
