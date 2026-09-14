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

COMO ESTE NUMERO FOI ESCOLHIDO
Contra 20 perguntas (12 que o acervo responde, 8 que nao), medidas sobre o
indice que `scripts/ingerir_documentos.py` produz de fato. As duas partes
dessa frase foram erradas antes e custaram um bug:

1. a primeira calibragem usou 5 perguntas, poucas demais pra distinguir
   sorte de separacao real;
2. e mediu sobre trechos escritos a mao, de uma frase, enquanto a ingestao
   gerava paragrafos inteiros — chunk maior fica mais distante de uma
   pergunta curta, e "qual o horario de atendimento?" acabava barrado
   apesar de estar na base.

Vale registrar tambem o *que* se mede. A calibragem seguinte ainda olhava so
"passou do limiar?", e deixou escapar o caso em que passa o trecho ERRADO:
"onde fica a loja?" trazia "Retirada na loja. Passado esse prazo, o pedido
volta para o estoque", porque o titulo da secao continha a palavra "loja".
Um trecho errado e pior que nenhum — o modelo recebe contexto plausivel e
responde com confianca a partir dele. A medicao boa e "o trecho certo veio?",
nao "veio alguma coisa?".

O QUE 0.65 ENTREGA, MEDIDO
     9 das 12 cobertas trazem o trecho CERTO
     1 traz o trecho errado ("como faco pra falar por e-mail?" cai no
       paragrafo de acompanhamento de pedido, que menciona e-mail)
     2 sao barradas e escalam a toa (ver abaixo)
     8 das 8 descobertas param aqui, sem gastar chamada de LLM

A FRONTEIRA, MEDIDA
    0.6372  coberta   a loja abre no domingo?      <- ultima que passa
    ------------------------------------------------ 0.65
    0.6640  coberta   onde fica a loja?            <- barrada
    0.6722  FORA      voces tem loja em Curitiba?
    0.6912  FORA      qual o CNPJ da empresa?
    0.7527  coberta   voces abrem no sabado?       <- barrada

A margem e de 0.035, o maior vao disponivel. Repare que "voces abrem no
sabado?" fica a 0.7527, mais longe que quatro perguntas que o acervo nem
cobre: o paragrafo de horarios e dominado por "segunda a sexta", e a frase
sobre sabado pesa pouco nele. E o preco de manter o paragrafo inteiro — que
ainda assim compensa (ver `trechos_de_markdown`).

POR QUE NAO AFROUXAR PRA 0.68 E GANHAR AS DUAS BARRADAS
Porque em 0.68 entram junto "voces tem loja em Curitiba?" e "qual o CNPJ da
empresa?", que o acervo nao responde. Ai a decisao volta a depender do
`deve_escalar` do modelo — que na medicao da Fase 3.1 errou com frequencia.
Preferimos a falha segura: uma pergunta sobre sabado indo pro humano a toa
custa menos que um CNPJ inventado chegando ao cliente. E o mesmo criterio
que motivou as Fases 3.1 e 4.

Calibrado pra ESTE acervo e ESTE modelo de embeddings: mudar qualquer um dos
dois pede remedir. Sobrescrevivel no construtor.
"""

TRECHOS_POR_BUSCA_PADRAO = 3
"""Quantos trechos no maximo entram no prompt, antes de aplicar o limiar."""

PREFIXO_DE_SECAO = "{secao}. {texto}"
"""Como o titulo da secao entra no trecho indexado.

O titulo carrega o assunto que o texto muitas vezes nao repete: o paragrafo
sob "## Horario de funcionamento" fala em "segunda a sexta" e "9h as 18h",
mas nunca escreve "horario de atendimento". Sem o titulo, a pergunta obvia
do cliente nao encontra o trecho que a responde — foi o que aconteceu.
Manter o titulo reduziu os conflitos de fronteira de 9 pra 4 na medicao.
"""


def trechos_de_markdown(pasta: str | Path) -> list[str]:
    """Le os `.md` da pasta e devolve os trechos prontos pra indexar.

    Um paragrafo por trecho, prefixado pelo titulo da secao a que pertence.
    As duas decisoes foram medidas, nao chutadas.

    O PARAGRAFO INTEIRO, E NAO UMA FRASE POR TRECHO
    Tentamos quebrar por frase, na intuicao de que trechos curtos casariam
    melhor com perguntas curtas. Medido, e pior: as tres frases sob
    "## Horario de funcionamento" (segunda a sexta, sabado, domingo) ficam
    quase equidistantes de "qual o horario de atendimento?", porque o que
    casa com a pergunta e o titulo, que todas compartilham. Qual delas vence
    vira sorteio, e a busca passou a devolver "aos domingos nao abre" pra
    quem perguntou o horario. Mantendo o paragrafo, as tres informacoes
    chegam juntas e o modelo responde completo.

    Vive aqui, e nao no script de ingestao, pelo mesmo motivo que
    `construir_indice`: o que a ingestao produz precisa ser exatamente o que
    os testes exercitam. Foi justamente essa divergencia que fez o limiar
    nascer calibrado errado.
    """
    trechos: list[str] = []
    for arquivo in sorted(Path(pasta).glob("*.md")):
        secao = ""
        for bloco in arquivo.read_text(encoding="utf-8").split("\n\n"):
            limpo = " ".join(bloco.split())
            if not limpo:
                continue
            if limpo.startswith("##"):
                secao = limpo.lstrip("# ").strip()
            elif limpo.startswith("#"):
                secao = ""  # titulo do documento: nao rotula secao nenhuma
            elif secao:
                trechos.append(PREFIXO_DE_SECAO.format(secao=secao, texto=limpo))
            else:
                trechos.append(limpo)
    return trechos


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
