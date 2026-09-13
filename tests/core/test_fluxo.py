"""Testes de `processar_mensagem_recebida` — o fluxo inteiro, ponta a ponta.

As quatro portas sao satisfeitas por classes falsas definidas aqui mesmo.
Repare que nenhuma delas herda de `core.ports`: sao aceitas porque tem os
metodos certos, e e exatamente isso que `Protocol` promete. Nenhum framework
de mock, nenhuma rede, nenhum arquivo.
"""

from datetime import datetime

from core.conversa import Autor, Conversa, Mensagem, StatusConversa
from core.ports import RespostaLLM
from core.triagem import Decisao, TriagemService, processar_mensagem_recebida

AGORA = datetime(2026, 9, 13, 14, 30)


class FakeBaseConhecimento:
    """Devolve sempre os mesmos trechos, e anota o que lhe perguntaram."""

    def __init__(self, trechos: list[str] | None = None) -> None:
        self.trechos = trechos if trechos is not None else ["trecho A", "trecho B"]
        self.perguntas_recebidas: list[str] = []

    def buscar_trechos_relevantes(self, pergunta: str) -> list[str]:
        self.perguntas_recebidas.append(pergunta)
        return list(self.trechos)


class FakeProvedorLLM:
    """Devolve a resposta combinada no construtor, e guarda o que recebeu."""

    def __init__(self, texto: str, deve_escalar: bool = False) -> None:
        self.resposta = RespostaLLM(texto=texto, deve_escalar=deve_escalar)
        self.mensagens_recebidas: list[tuple[Mensagem, ...]] = []
        self.trechos_recebidos: list[list[str]] = []

    def gerar_resposta(self, mensagens, trechos_contexto: list[str]) -> RespostaLLM:
        self.mensagens_recebidas.append(tuple(mensagens))
        self.trechos_recebidos.append(list(trechos_contexto))
        return self.resposta


class FakeCanal:
    """Nao envia nada — so anota o que teria enviado."""

    def __init__(self) -> None:
        self.enviadas: list[tuple[str, str]] = []

    def enviar_mensagem(self, conversa_id: str, texto: str) -> None:
        self.enviadas.append((conversa_id, texto))


class FakeGatewayHandoff:
    """Nao escala nada — so anota os pedidos de escalonamento."""

    def __init__(self) -> None:
        self.escalonamentos: list[tuple[Conversa, str, dict]] = []

    def escalar(self, conversa: Conversa, resumo: str, atributos: dict) -> None:
        self.escalonamentos.append((conversa, resumo, atributos))


def _processar(
    conversa,
    texto_do_llm,
    deve_escalar=False,
    texto_cliente="qual o horario?",
    limite=3,
):
    """Roda o fluxo com fakes, e devolve o resultado junto dos fakes usados."""
    base = FakeBaseConhecimento()
    llm = FakeProvedorLLM(texto_do_llm, deve_escalar=deve_escalar)
    canal = FakeCanal()
    handoff = FakeGatewayHandoff()

    resultado = processar_mensagem_recebida(
        conversa=conversa,
        texto_cliente=texto_cliente,
        timestamp=AGORA,
        base_conhecimento=base,
        provedor_llm=llm,
        triagem=TriagemService(limite_tentativas=limite),
        canal=canal,
        gateway_handoff=handoff,
    )
    return resultado, base, llm, canal, handoff


def _conversa_com_respostas_da_ia(quantidade: int) -> Conversa:
    """Conversa onde a IA ja respondeu `quantidade` vezes sem resolver."""
    conversa = Conversa(conversa_id="c1")
    for i in range(quantidade):
        conversa.registrar_mensagem(
            Mensagem(Autor.CLIENTE, f"pergunta {i}", datetime(2026, 9, 13, 10, i * 2))
        )
        conversa.registrar_mensagem(
            Mensagem(Autor.IA, f"resposta {i}", datetime(2026, 9, 13, 10, i * 2 + 1))
        )
    return conversa


class TestQuandoAIAResolve:
    def test_devolve_decisao_de_resolver(self):
        resultado, *_ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert resultado.decisao is Decisao.RESOLVER

    def test_a_resposta_chega_ao_cliente_pelo_canal(self):
        _, _, _, canal, _ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert canal.enviadas == [("c1", "Das 9h as 18h.")]

    def test_o_handoff_nao_e_acionado(self):
        *_, handoff = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert handoff.escalonamentos == []

    def test_a_conversa_continua_ativa(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.")

        assert conversa.status is StatusConversa.ATIVA

    def test_o_historico_guarda_a_pergunta_e_a_resposta_nessa_ordem(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.", texto_cliente="qual o horario?")

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "qual o horario?", AGORA),
            Mensagem(Autor.IA, "Das 9h as 18h.", AGORA),
        )

    def test_o_historico_guarda_o_texto_e_nao_a_RespostaLLM_inteira(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "Das 9h as 18h.")

        ultima = conversa.mensagens[-1]
        assert isinstance(ultima.conteudo, str)
        assert ultima.conteudo == "Das 9h as 18h."


class TestOQueOFluxoEntregaAsPortas:
    def test_a_base_de_conhecimento_recebe_a_pergunta_do_cliente(self):
        _, base, _, _, _ = _processar(
            Conversa(conversa_id="c1"), "Das 9h as 18h.", texto_cliente="qual o horario?"
        )

        assert base.perguntas_recebidas == ["qual o horario?"]

    def test_o_llm_recebe_os_trechos_da_base_de_conhecimento(self):
        _, base, llm, _, _ = _processar(Conversa(conversa_id="c1"), "Das 9h as 18h.")

        assert llm.trechos_recebidos == [base.trechos]

    def test_o_llm_recebe_o_historico_ja_com_a_pergunta_atual(self):
        conversa = Conversa(conversa_id="c1")

        _, _, llm, _, _ = _processar(
            conversa, "Das 9h as 18h.", texto_cliente="qual o horario?"
        )

        assert llm.mensagens_recebidas == [
            (Mensagem(Autor.CLIENTE, "qual o horario?", AGORA),)
        ]

    def test_o_llm_nao_ve_a_propria_resposta_candidata(self):
        conversa = _conversa_com_respostas_da_ia(1)

        _, _, llm, _, _ = _processar(conversa, "Das 9h as 18h.")

        assert all(
            mensagem.conteudo != "Das 9h as 18h." for mensagem in llm.mensagens_recebidas[0]
        )


class TestQuandoAIAPedeParaEscalar:
    def test_devolve_decisao_de_escalar(self):
        resultado, *_ = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert resultado.decisao is Decisao.ESCALAR

    def test_o_handoff_recebe_o_motivo_da_triagem(self):
        resultado, _, _, _, handoff = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert [resumo for _, resumo, _ in handoff.escalonamentos] == [resultado.motivo]

    def test_o_handoff_recebe_a_conversa_ja_escalada(self):
        conversa = Conversa(conversa_id="c1")

        _, _, _, _, handoff = _processar(conversa, "vou transferir", deve_escalar=True)

        (conversa_escalada, _, _) = handoff.escalonamentos[0]
        assert conversa_escalada is conversa
        assert conversa_escalada.status is StatusConversa.ESCALADA

    def test_o_cliente_nao_recebe_nada_pelo_canal(self):
        _, _, _, canal, _ = _processar(
            Conversa(conversa_id="c1"), "nao sei responder", deve_escalar=True
        )

        assert canal.enviadas == []

    def test_a_conversa_fica_escalada(self):
        conversa = Conversa(conversa_id="c1")

        _processar(conversa, "vou transferir", deve_escalar=True)

        assert conversa.status is StatusConversa.ESCALADA

    def test_a_resposta_candidata_nao_entra_no_historico(self):
        conversa = Conversa(conversa_id="c1")

        _processar(
            conversa, "nao sei", deve_escalar=True, texto_cliente="pergunta dificil"
        )

        assert conversa.mensagens == (
            Mensagem(Autor.CLIENTE, "pergunta dificil", AGORA),
        )

    def test_um_texto_que_parece_resposta_normal_ainda_escala(self):
        """A decisao vem do campo, nao de inspecionar o texto."""
        conversa = Conversa(conversa_id="c1")

        _, _, _, canal, handoff = _processar(
            conversa, "Das 9h as 18h.", deve_escalar=True
        )

        assert canal.enviadas == []
        assert len(handoff.escalonamentos) == 1


class TestQuandoEstouraOLimiteDeTentativas:
    def test_a_quarta_pergunta_escala_com_limite_de_tres(self):
        conversa = _conversa_com_respostas_da_ia(3)

        resultado, *_ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert resultado.decisao is Decisao.ESCALAR

    def test_a_terceira_pergunta_ainda_e_respondida_com_limite_de_tres(self):
        conversa = _conversa_com_respostas_da_ia(2)

        resultado, _, _, canal, _ = _processar(
            conversa, "Tente reiniciar o app.", limite=3
        )

        assert resultado.decisao is Decisao.RESOLVER
        assert canal.enviadas == [("c1", "Tente reiniciar o app.")]

    def test_o_motivo_cita_as_tentativas_e_nao_o_pedido_da_ia(self):
        conversa = _conversa_com_respostas_da_ia(3)

        resultado, *_ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert "3" in resultado.motivo

    def test_o_cliente_nao_recebe_a_resposta_fraca(self):
        conversa = _conversa_com_respostas_da_ia(3)

        _, _, _, canal, _ = _processar(conversa, "Tente reiniciar o app.", limite=3)

        assert canal.enviadas == []
