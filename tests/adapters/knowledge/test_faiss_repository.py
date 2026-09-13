"""Testes do `FaissBaseConhecimento` — com embeddings e indice de verdade.

Sem mock: cada teste gera embeddings reais pelo Ollama e monta um indice
FAISS real, num diretorio temporario.

O ponto mais importante deste modulo: o indice e construido a partir dos
documentos de `data/documentos/`, pelo mesmo `trechos_de_markdown` que o
script de ingestao usa. A versao anterior montava o indice com trechos
escritos a mao dentro do teste — passava verde enquanto o pipeline real
produzia chunks diferentes, e foi assim que um limiar calibrado errado
chegou ate a `dev`. Um teste que nao usa o caminho de producao mede outra
coisa.

Se o Ollama nao estiver de pe ou o modelo de embeddings nao estiver
baixado, os testes sao pulados com a mensagem do que falta.
"""

import os
from pathlib import Path

import pytest
import requests

from adapters.knowledge.faiss_repository import (
    DISTANCIA_MAXIMA_PADRAO,
    MODELO_EMBEDDINGS_PADRAO,
    FaissBaseConhecimento,
    construir_indice,
    trechos_de_markdown,
)

BASE_URL_PADRAO = "http://localhost:11434"
PASTA_DOCUMENTOS = Path(__file__).resolve().parents[3] / "data" / "documentos"

# (pergunta, trecho da resposta que PRECISA vir no resultado)
# Nao basta "veio alguma coisa": um trecho errado e pior que nenhum, porque
# da ao modelo um contexto plausivel pra responder com confianca. Foi esse
# caso — "onde fica a loja?" trazendo o trecho sobre retirada de pedidos —
# que a versao anterior destes testes nao viu.
PERGUNTAS_COBERTAS = [
    ("qual o horario de atendimento?", "segunda a sexta"),
    ("a loja abre no domingo?", "domingo"),
    ("ate que horas voces ficam abertos na sexta?", "18h"),
    ("qual o endereco de voces?", "Paulista"),
    ("qual o telefone de contato?", "4000-1000"),
    ("como acompanho meu pedido?", "acompanha"),
    ("posso cancelar meu pedido?", "cancelado"),
    ("da pra alterar um pedido ja despachado?", "despachado"),
    ("quanto tempo o pedido fica guardado pra retirada?", "7 dias"),
]

PERGUNTAS_FORA_DO_ACERVO = [
    "qual a politica de reembolso de voces?",
    "quanto custa o frete pra Manaus?",
    "voces parcelam no cartao?",
    "qual a garantia dos produtos?",
    "como faco pra trocar um produto com defeito?",
    "qual o CNPJ da empresa?",
    "voces tem loja em Curitiba?",
    "qual a capital da Mongolia?",
]

COBERTAS_QUE_O_LIMIAR_BARRA = [
    # O acervo responde as duas, mas elas ficam acima de 0.65 e escalam pro
    # humano a toa. E o preco escolhido: afrouxar pra pegar estas deixaria
    # passar "voces tem loja em Curitiba?" e "qual o CNPJ da empresa?", que
    # o acervo nao responde. Ver DISTANCIA_MAXIMA_PADRAO.
    "voces abrem no sabado?",
    "onde fica a loja?",
]

COBERTAS_COM_RECUPERACAO_ERRADA = [
    # Passa do limiar, mas traz o paragrafo de acompanhamento de pedido (que
    # menciona e-mail) em vez do de contato. Fica travado aqui pra que seja
    # um defeito conhecido e visivel, e nao uma surpresa em producao.
    "como faco pra falar com voces por e-mail?",
]


@pytest.fixture(scope="session")
def base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", BASE_URL_PADRAO)


@pytest.fixture(scope="session")
def ollama_com_embeddings(base_url: str) -> str:
    """Garante que da pra gerar embeddings, ou pula explicando o que falta."""
    modelo = os.environ.get("OLLAMA_EMBEDDINGS_MODEL", MODELO_EMBEDDINGS_PADRAO)
    try:
        resposta = requests.get(f"{base_url}/api/tags", timeout=5)
        resposta.raise_for_status()
        disponiveis = [m["name"] for m in resposta.json().get("models", [])]
    except requests.RequestException as erro:
        pytest.skip(
            f"Ollama nao respondeu em {base_url} ({erro.__class__.__name__}). "
            "Suba com `ollama serve` pra rodar este teste."
        )

    if not any(nome.split(":")[0] == modelo.split(":")[0] for nome in disponiveis):
        pytest.skip(
            f"o modelo de embeddings {modelo} nao esta baixado. "
            f"Rode `ollama pull {modelo}`. Disponiveis: {', '.join(disponiveis)}."
        )
    return modelo


@pytest.fixture(scope="session")
def indice_em_disco(tmp_path_factory, base_url, ollama_com_embeddings):
    """Indice real, montado pelo mesmo caminho que o script de ingestao usa."""
    caminho = tmp_path_factory.mktemp("faiss_indice")
    construir_indice(
        trechos_de_markdown(PASTA_DOCUMENTOS),
        caminho_destino=caminho,
        base_url=base_url,
        modelo_embeddings=ollama_com_embeddings,
    )
    return caminho


@pytest.fixture
def base(indice_em_disco, base_url, ollama_com_embeddings) -> FaissBaseConhecimento:
    return FaissBaseConhecimento(
        caminho_indice=indice_em_disco,
        base_url=base_url,
        modelo_embeddings=ollama_com_embeddings,
    )


class TestTrechosDeMarkdown:
    """A leitura dos documentos, sem rede — nao precisa de Ollama."""

    def test_le_os_documentos_do_projeto(self):
        assert trechos_de_markdown(PASTA_DOCUMENTOS) != []

    def test_cada_trecho_carrega_o_titulo_da_secao(self):
        """Sem o titulo, "qual o horario de atendimento?" nao acha o trecho
        que o responde — o paragrafo fala em "9h as 18h" e nunca escreve
        "horario de atendimento"."""
        trechos = trechos_de_markdown(PASTA_DOCUMENTOS)

        assert any(t.startswith("Horário de funcionamento.") for t in trechos)
        assert any(t.startswith("Endereço.") for t in trechos)

    def test_nenhum_trecho_e_so_um_titulo_de_markdown(self):
        trechos = trechos_de_markdown(PASTA_DOCUMENTOS)

        assert not any(t.lstrip().startswith("#") for t in trechos)

    def test_quebra_em_frases_e_nao_em_paragrafos(self):
        """Paragrafo que mistura assuntos fica longe de todas as perguntas.

        Mede o tamanho, e nao a contagem de pontos: um e-mail ou um CEP tem
        pontos que nao terminam frase.
        """
        trechos = trechos_de_markdown(PASTA_DOCUMENTOS)

        assert all(len(t) < 200 for t in trechos)

    def test_pasta_vazia_devolve_lista_vazia(self, tmp_path):
        assert trechos_de_markdown(tmp_path) == []


class TestPerguntasQueOAcervoResponde:
    @pytest.mark.parametrize("pergunta,esperado", PERGUNTAS_COBERTAS)
    def test_traz_o_trecho_certo(self, base, pergunta, esperado):
        """Nao basta vir algo: precisa vir o trecho que responde a pergunta."""
        trechos = base.buscar_trechos_relevantes(pergunta)

        assert trechos, f"nada foi recuperado para: {pergunta}"
        assert any(esperado.lower() in t.lower() for t in trechos), (
            f"para '{pergunta}' esperava um trecho com '{esperado}', "
            f"veio: {trechos}"
        )

    def test_os_trechos_sao_strings(self, base):
        trechos = base.buscar_trechos_relevantes("qual o horario de atendimento?")

        assert all(isinstance(t, str) and t.strip() for t in trechos)

    def test_o_trecho_mais_relevante_vem_primeiro(self, base):
        trechos = base.buscar_trechos_relevantes("a loja abre no domingo?")

        assert "domingo" in trechos[0].lower()



class TestPerguntasForaDoAcervo:
    @pytest.mark.parametrize("pergunta", PERGUNTAS_FORA_DO_ACERVO)
    def test_devolve_lista_vazia(self, base, pergunta):
        assert base.buscar_trechos_relevantes(pergunta) == []


class TestOLimiteConhecidoDoMetodo:
    """Trava o que o limiar NAO resolve, pra que seja visivel e nao surpresa.

    Se um dia estas mudarem de comportamento (acervo melhor, modelo de
    embeddings melhor), o teste quebra e obriga a revisar o docstring de
    `DISTANCIA_MAXIMA_PADRAO`, que hoje descreve exatamente estes casos.
    """

    @pytest.mark.parametrize("pergunta", COBERTAS_QUE_O_LIMIAR_BARRA)
    def test_coberta_perto_da_fronteira_escala_a_toa(self, base, pergunta):
        assert base.buscar_trechos_relevantes(pergunta) == []

    @pytest.mark.parametrize("pergunta", COBERTAS_COM_RECUPERACAO_ERRADA)
    def test_coberta_que_traz_o_paragrafo_errado(self, base, pergunta):
        """Passa do limiar, mas com o trecho errado — o pior dos casos.

        Fica travado pra ser defeito conhecido, e nao surpresa: o modelo
        recebe contexto plausivel e responde com confianca a partir dele.
        """
        assert base.buscar_trechos_relevantes(pergunta) != []


class TestOLimiar:
    def test_e_distancia_entao_limiar_alto_deixa_passar_mais(
        self, base_url, indice_em_disco, ollama_com_embeddings
    ):
        """Trava a convencao: score e distancia, menor e mais parecido.

        Se alguem inverter a comparacao, este teste quebra — com um limiar
        generoso ate a pergunta absurda passa, e com um limiar apertado nem
        a pergunta coberta passa.
        """
        generosa = FaissBaseConhecimento(
            caminho_indice=indice_em_disco,
            base_url=base_url,
            modelo_embeddings=ollama_com_embeddings,
            distancia_maxima=99.0,
        )
        apertada = FaissBaseConhecimento(
            caminho_indice=indice_em_disco,
            base_url=base_url,
            modelo_embeddings=ollama_com_embeddings,
            distancia_maxima=0.0,
        )

        assert generosa.buscar_trechos_relevantes("qual a capital da Mongolia?") != []
        assert apertada.buscar_trechos_relevantes("a loja abre no domingo?") == []

    def test_a_base_usa_o_valor_padrao(self, base):
        assert base.distancia_maxima == DISTANCIA_MAXIMA_PADRAO

    def test_devolve_no_maximo_o_numero_pedido_de_trechos(
        self, base_url, indice_em_disco, ollama_com_embeddings
    ):
        limitada = FaissBaseConhecimento(
            caminho_indice=indice_em_disco,
            base_url=base_url,
            modelo_embeddings=ollama_com_embeddings,
            distancia_maxima=99.0,
            trechos_por_busca=2,
        )

        assert len(limitada.buscar_trechos_relevantes("qual o horario?")) == 2
