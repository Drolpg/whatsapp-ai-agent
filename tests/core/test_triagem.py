"""Testes do `TriagemService` — a decisao entre resolver e escalar.

Objetos Python puros: nenhuma chamada de rede, nenhum arquivo, nenhum mock.
A resposta candidata da IA e uma `RespostaLLM`; quem a produziu (Ollama,
Anthropic, ou este teste) nao faz diferenca pra decisao.
"""

from datetime import datetime

import pytest

from core.conversa import Autor, Conversa, Mensagem
from core.ports import RespostaLLM
from core.triagem import (
    MENSAGEM_FORA_DO_DOMINIO,
    Decisao,
    TriagemService,
)


def _resposta(texto: str = "O horario e das 9h as 18h.", escalar: bool = False) -> RespostaLLM:
    return RespostaLLM(texto=texto, deve_escalar=escalar)


def _conversa_com(tentativas_da_ia: int = 0, respostas_uteis: int = 0) -> Conversa:
    """Conversa com `tentativas_da_ia` respostas sem fundamento no fim.

    `respostas_uteis` acrescenta antes delas respostas fundamentadas — que
    NAO sao tentativas frustradas e nao podem contar pro limite.
    """
    conversa = Conversa(conversa_id="c1")
    minuto = 0
    for i in range(respostas_uteis):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta boa {i}", datetime(2026, 9, 12, 10, minuto))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, f"resposta util {i}", datetime(2026, 9, 12, 10, minuto + 1))
        )
        minuto += 2
    for i in range(tentativas_da_ia):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 12, 10, minuto))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, MENSAGEM_FORA_DO_DOMINIO, datetime(2026, 9, 12, 10, minuto + 1))
        )
        minuto += 2
    return conversa


class TestResolvidoSemEscalar:
    def test_resposta_normal_em_conversa_nova_resolve(self):
        resultado = TriagemService().decidir(_conversa_com(), _resposta())

        assert resultado.decisao is Decisao.RESOLVER

    def test_o_texto_da_ia_e_preservado_intacto(self):
        resultado = TriagemService().decidir(
            _conversa_com(), _resposta("O horario e das 9h as 18h.")
        )

        assert resultado.resposta == "O horario e das 9h as 18h."

    def test_resolve_enquanto_estiver_dentro_do_limite_de_tentativas(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(
            _conversa_com(tentativas_da_ia=2), _resposta("Tente reiniciar o app.")
        )

        assert resultado.decisao is Decisao.RESOLVER


class TestEscaladoPorPedidoExplicitoDaIA:
    def test_deve_escalar_verdadeiro_escala(self):
        resultado = TriagemService().decidir(
            _conversa_com(), _resposta("nao tenho essa informacao", escalar=True)
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_escala_mesmo_na_primeira_mensagem_da_conversa(self):
        conversa = _conversa_com(tentativas_da_ia=0)

        resultado = TriagemService(limite_tentativas=3).decidir(
            conversa, _resposta("vou transferir", escalar=True)
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_texto_da_resposta_nao_interfere_na_decisao(self):
        """O campo manda, nao o conteudo do texto.

        Antes a decisao dependia de achar um marcador dentro da string, e o
        modelo podia corrompe-lo. Agora um texto que *parece* uma resposta
        normal ainda escala se o campo disser que sim.
        """
        resultado = TriagemService().decidir(
            _conversa_com(), _resposta("O horario e das 9h as 18h.", escalar=True)
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_texto_que_menciona_escalar_nao_escala_sozinho(self):
        resultado = TriagemService().decidir(
            _conversa_com(), _resposta("[ESCALAR] isso aqui e so texto", escalar=False)
        )

        assert resultado.decisao is Decisao.RESOLVER

    def test_o_motivo_explica_que_partiu_da_ia(self):
        resultado = TriagemService().decidir(_conversa_com(), _resposta(escalar=True))

        assert "IA" in resultado.motivo

    def test_nao_sobra_resposta_para_enviar_ao_cliente(self):
        resultado = TriagemService().decidir(_conversa_com(), _resposta(escalar=True))

        assert resultado.resposta is None


class TestRespostasUteisNaoContamComoTentativa:
    """O defeito que este teste tranca: cliente satisfeito sendo escalado.

    O contador somava TODAS as mensagens da IA, entao quem fizesse quatro
    perguntas e recebesse quatro respostas certas era transferido pro humano
    na quarta. O docstring sempre disse "tentativas sem sucesso" — era a
    implementacao que contava sucesso junto.
    """

    def test_quatro_respostas_certas_nao_escalam(self):
        conversa = _conversa_com(respostas_uteis=4)

        resultado = TriagemService(limite_tentativas=3).decidir(
            conversa, _resposta("Mais uma resposta boa.")
        )

        assert resultado.decisao is Decisao.RESOLVER

    def test_dez_respostas_certas_nao_escalam(self):
        conversa = _conversa_com(respostas_uteis=10)

        resultado = TriagemService(limite_tentativas=3).decidir(
            conversa, _resposta("Ainda ajudando.")
        )

        assert resultado.decisao is Decisao.RESOLVER

    def test_uma_resposta_util_zera_a_sequencia(self):
        """Depois de ajudar, a IA ganha a contagem de volta do zero."""
        conversa = _conversa_com(tentativas_da_ia=2)
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, "e o horario?", datetime(2026, 9, 12, 11, 0))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, "Das 9h as 18h.", datetime(2026, 9, 12, 11, 1))
        )

        resultado = TriagemService(limite_tentativas=3).decidir(
            conversa, _resposta("outra resposta")
        )

        assert resultado.decisao is Decisao.RESOLVER


class TestEscaladoPorNumeroDeTentativas:
    def test_escala_quando_a_ia_ja_tentou_o_limite_de_vezes(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(
            _conversa_com(tentativas_da_ia=3), _resposta("Tente de novo mais tarde.")
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_motivo_cita_o_numero_de_tentativas(self):
        servico = TriagemService(limite_tentativas=3)

        resultado = servico.decidir(
            _conversa_com(tentativas_da_ia=3), _resposta("Tente de novo.")
        )

        assert "3" in resultado.motivo

    def test_o_limite_e_configuravel(self):
        servico = TriagemService(limite_tentativas=1)

        resultado = servico.decidir(
            _conversa_com(tentativas_da_ia=1), _resposta("Tente de novo.")
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_mensagens_do_cliente_nao_contam_como_tentativa_da_ia(self):
        conversa = Conversa(conversa_id="c1")
        for i in range(5):
            conversa.registrar_mensagem(
                Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 12, 10, i))
            )

        resultado = TriagemService(limite_tentativas=3).decidir(
            conversa, _resposta("Claro, posso ajudar.")
        )

        assert resultado.decisao is Decisao.RESOLVER


class TestLimiteInvalido:
    def test_limite_menor_que_um_e_recusado_na_construcao(self):
        with pytest.raises(ValueError):
            TriagemService(limite_tentativas=0)
