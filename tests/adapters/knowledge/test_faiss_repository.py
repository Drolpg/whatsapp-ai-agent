"""Testes do `FaissBaseConhecimento` — com embeddings e indice de verdade.

Sem mock: cada teste gera embeddings reais pelo Ollama e monta um indice
FAISS real. O indice e construido na hora, num diretorio temporario, em vez
de depender do que `scripts/ingerir_documentos.py` deixou em disco — assim o
teste roda do zero em qualquer maquina, e o que ele exercita e o mesmo
codigo de construcao que o script usa.

Se o Ollama nao estiver de pe ou o modelo de embeddings nao estiver
baixado, os testes sao pulados com a mensagem do que falta.
"""

import os

import pytest
import requests

from adapters.knowledge.faiss_repository import (
    DISTANCIA_MAXIMA_PADRAO,
    MODELO_EMBEDDINGS_PADRAO,
    FaissBaseConhecimento,
    construir_indice,
)

BASE_URL_PADRAO = "http://localhost:11434"

TRECHOS = [
    "O horario de atendimento da loja e de segunda a sexta, das 9h as 18h.",
    "Aos sabados a loja abre das 9h as 13h. Aos domingos a loja nao abre.",
    "A loja fica na Avenida Paulista, 1000, em Sao Paulo.",
    "O telefone de contato da loja e (11) 4000-1000.",
    "Pedidos para retirada ficam disponiveis por 7 dias corridos.",
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
    """Constroi um indice FAISS real a partir de `TRECHOS` e salva em disco."""
    caminho = tmp_path_factory.mktemp("faiss_indice")
    construir_indice(
        TRECHOS,
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


class TestQuandoAPerguntaEstaCobertaPelaBase:
    def test_traz_trechos(self, base):
        trechos = base.buscar_trechos_relevantes("a loja abre no domingo?")

        assert trechos != []

    def test_os_trechos_sao_strings_do_acervo(self, base):
        trechos = base.buscar_trechos_relevantes("a loja abre no domingo?")

        assert all(isinstance(t, str) for t in trechos)
        assert all(t in TRECHOS for t in trechos)

    def test_o_trecho_mais_relevante_vem_primeiro(self, base):
        trechos = base.buscar_trechos_relevantes("a loja abre no domingo?")

        assert "domingo" in trechos[0].lower()

    def test_uma_pergunta_sobre_endereco_traz_o_trecho_do_endereco(self, base):
        trechos = base.buscar_trechos_relevantes("onde fica a loja?")

        assert any("Paulista" in t for t in trechos)


class TestQuandoNadaNoAcervoServe:
    def test_pergunta_sem_relacao_nenhuma_devolve_lista_vazia(self, base):
        trechos = base.buscar_trechos_relevantes("qual a capital da Mongolia?")

        assert trechos == []

    def test_pergunta_de_outro_assunto_de_atendimento_devolve_lista_vazia(self, base):
        """Reembolso e plausivel num atendimento, mas nao esta neste acervo."""
        trechos = base.buscar_trechos_relevantes("qual a politica de reembolso de voces?")

        assert trechos == []


class TestOLimiar:
    def test_e_uma_distancia_entao_limiar_alto_deixa_passar_mais(self, base_url, indice_em_disco, ollama_com_embeddings):
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

    def test_o_padrao_separa_coberto_de_nao_coberto(self, base):
        """O valor padrao precisa dar conta dos dois lados da fronteira."""
        assert base.distancia_maxima == DISTANCIA_MAXIMA_PADRAO
        assert base.buscar_trechos_relevantes("qual o horario de atendimento?") != []
        assert base.buscar_trechos_relevantes("quanto custa o frete pra Manaus?") == []
