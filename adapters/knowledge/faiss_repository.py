"""`FaissBaseConhecimento` — implementa `BaseConhecimento` com FAISS.

Indexa a Base de Conhecimento com LangChain e embeddings locais, guarda os
vetores em um indice FAISS em disco e, a cada pergunta, devolve os trechos
mais relevantes.

O modelo de embeddings e o `nomic-embed-text`, servido pelo mesmo Ollama que
ja atende o `ProvedorLLM`. Tres motivos: roda local (nenhum dado do cliente
sai da maquina, custo zero), nao acrescenta dependencia pesada ao projeto —
`sentence-transformers` traria o PyTorch inteiro junto, enquanto aqui basta
uma chamada HTTP ao Ollama que ja esta de pe — e devolve vetores
normalizados, o que simplifica a leitura das distancias (ver abaixo).

CONVENCAO DE SCORE — o detalhe que e facil errar
`similarity_search_with_score` do FAISS devolve **distancia**, nao
similaridade: **quanto MENOR o numero, mais parecido**. Por isso o limiar se
chama `distancia_maxima` e a comparacao e `distancia <= limite`. O nome nao
e enfeite: "limiar de similaridade" convidaria a escrever `>=` e inverter o
comportamento em silencio — a busca passaria a devolver exatamente o que nao
tem a ver com a pergunta. Ha um teste em
`tests/adapters/knowledge/test_faiss_repository.py::TestOLimiar` que trava
essa direcao.

(Como o `nomic-embed-text` ja normaliza os vetores, as estrategias
EUCLIDEAN_DISTANCE e COSINE do LangChain produzem os mesmos numeros aqui.
Ficamos com a euclidiana, que e o padrao.)

A licao da Fase 4 e que o RAG nao e uma camada nova nem um caso especial —
e so mais um adapter atras de uma interface que ja existia. Mas ele ganhou
uma responsabilidade a mais: decidir se o acervo *cobre* a pergunta. Essa
decisao estava no prompt do LLM e nao funcionava (ver Fase 3.1 em
`tasks.md`); aqui ela vira uma comparacao numerica com um limiar, e "nao
cobre" se expressa como lista vazia — que o contrato de `BaseConhecimento`
ja previa.
"""

from collections.abc import Iterable
from pathlib import Path

from langchain_community.vectorstores import FAISS
from langchain_ollama import OllamaEmbeddings

MODELO_EMBEDDINGS_PADRAO = "nomic-embed-text"
"""Modelo de embeddings servido pelo Ollama. Baixe com `ollama pull`."""

DISTANCIA_MAXIMA_PADRAO = 0.65
"""Distancia maxima pra um trecho ser considerado relevante (menor = melhor).

Escolhido a partir dos scores medidos com o acervo de teste e as perguntas
do benchmark da Fase 3.1:

    a loja abre no domingo?          0.47   coberto
    qual o horario de atendimento?   0.54   coberto
    -------------------------------------- fronteira
    quanto custa o frete pra Manaus? 0.75   nao coberto
    qual a politica de reembolso?    0.94   nao coberto
    qual a capital da Mongolia?      1.01   nao coberto

0.65 fica no meio do vao entre 0.54 e 0.75, que e a maior folga disponivel.
E um valor calibrado pra ESTE acervo e ESTE modelo de embeddings: mudar
qualquer um dos dois pede remedir. Sobrescrevivel no construtor.
"""

TRECHOS_POR_BUSCA_PADRAO = 3
"""Quantos trechos no maximo entram no prompt, antes de aplicar o limiar."""


def construir_indice(
    textos: Iterable[str],
    caminho_destino: str | Path,
    base_url: str,
    modelo_embeddings: str = MODELO_EMBEDDINGS_PADRAO,
) -> None:
    """Gera os embeddings de `textos` e salva um indice FAISS em disco.

    Usado pelo script de ingestao e pelos testes — os dois passam pelo mesmo
    caminho, entao o que o teste exercita e o que o script produz.
    """
    indice = FAISS.from_texts(
        list(textos),
        OllamaEmbeddings(model=modelo_embeddings, base_url=base_url),
    )
    indice.save_local(str(caminho_destino))


class FaissBaseConhecimento:
    """Busca trechos relevantes num indice FAISS ja construido em disco.

    Como o `OllamaProvedorLLM`, recebe a configuracao pronta pelo construtor
    e nunca le `os.environ` — quem traduz ambiente em configuracao e o
    `main.py`. Isso e o que deixa um teste apontar pra um indice temporario
    sem mexer em variavel de ambiente nenhuma.

    Nao herda de `core.ports.BaseConhecimento`: satisfaz a porta por ter o
    metodo com a forma certa, que e o que `Protocol` verifica.
    """

    def __init__(
        self,
        caminho_indice: str | Path,
        base_url: str,
        modelo_embeddings: str = MODELO_EMBEDDINGS_PADRAO,
        distancia_maxima: float = DISTANCIA_MAXIMA_PADRAO,
        trechos_por_busca: int = TRECHOS_POR_BUSCA_PADRAO,
    ) -> None:
        self.distancia_maxima = distancia_maxima
        self.trechos_por_busca = trechos_por_busca
        self._indice = FAISS.load_local(
            str(caminho_indice),
            OllamaEmbeddings(model=modelo_embeddings, base_url=base_url),
            allow_dangerous_deserialization=True,
        )

    def buscar_trechos_relevantes(self, pergunta: str) -> list[str]:
        """Devolve os trechos relevantes, ou lista vazia se nenhum for.

        Lista vazia nao e um erro: e a resposta honesta de que o acervo nao
        cobre a pergunta. Quem chama (`processar_mensagem_recebida`) trata
        isso escalando pra um humano, sem nem consultar o LLM.
        """
        achados = self._indice.similarity_search_with_score(
            pergunta, k=self.trechos_por_busca
        )
        return [
            documento.page_content
            for documento, distancia in achados
            if distancia <= self.distancia_maxima
        ]
