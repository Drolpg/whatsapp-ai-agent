"""Portas: os contratos que o nucleo exige de quem fala com o mundo externo.

O nucleo precisa gerar texto, consultar documentos, enviar mensagens e
escalar atendimentos — mas nao deve saber *como* nada disso acontece. A
solucao e ele declarar aqui a forma do contrato (Protocols do Python) e
deixar `adapters/` implementar. Por isso as interfaces vivem em `core/` e
nao junto dos adapters: quem define o contrato e quem o consome, nao quem o
cumpre.

Sao `Protocol`, nao classes abstratas, e a diferenca importa: com `Protocol`
a compatibilidade e estrutural. Um adapter satisfaz a porta por ter os
metodos certos, sem precisar herdar nada daqui — ou seja, sem nem precisar
importar `core/`. A checagem acontece na tipagem estatica, nao em tempo de
execucao. E a forma mais literal de dizer "o nucleo nao conhece os
adapters".

E o que torna possivel o requisito central da POC: hoje o `ProvedorLLM` e
um Llama local, amanha pode ser uma API paga, e nenhuma linha de `core/`
muda — so o adapter escolhido no `main.py`.
"""

from collections.abc import Sequence
from typing import Protocol

from core.conversa import Conversa, Mensagem


class ProvedorLLM(Protocol):
    """Quem transforma a conversa ate aqui em uma resposta candidata."""

    def gerar_resposta(
        self, mensagens: Sequence[Mensagem], trechos_contexto: list[str]
    ) -> str:
        """Gera a proxima resposta da IA.

        Recebe o historico da conversa (a ultima mensagem e a pergunta que
        precisa ser respondida) e os trechos de apoio ja recuperados. Devolve
        texto puro, do jeito que iria pro cliente.

        A implementacao decide sozinha como montar o prompt e que modelo
        usar. O nucleo so espera duas coisas: que a resposta considere o
        historico, e que ela comece com o marcador de escalonamento quando o
        modelo nao souber responder — e o unico canal que ele tem pra pedir
        ajuda, ja que o retorno e uma string.
        """
        ...


class BaseConhecimento(Protocol):
    """De onde saem os trechos que fundamentam a resposta."""

    def buscar_trechos_relevantes(self, pergunta: str) -> list[str]:
        """Devolve os trechos de apoio pra responder `pergunta`.

        Cada trecho e um pedaco de texto pronto pra ir no prompt. Quantos
        devolver, como medir relevancia e como o acervo foi indexado sao
        decisoes da implementacao — o nucleo so consome a lista, em ordem
        de relevancia.

        Devolver lista vazia e uma resposta valida: significa que nada no
        acervo ajuda com essa pergunta, e cabe ao modelo lidar com isso.
        """
        ...


class Canal(Protocol):
    """Por onde a resposta chega ao cliente."""

    def enviar_mensagem(self, conversa_id: str, texto: str) -> None:
        """Entrega `texto` ao cliente da conversa `conversa_id`.

        O nucleo trata a entrega como concluida quando a chamada retorna sem
        erro; formato do canal, reentrega e confirmacao de leitura sao
        problema da implementacao.

        O caminho inverso — mensagens do cliente chegando — nao esta nesta
        porta de proposito: quem recebe e a implementacao, que chama
        `processar_mensagem_recebida`. O nucleo nunca fica esperando nada.
        """
        ...


class GatewayHandoff(Protocol):
    """Como uma conversa sai da IA e vai pra um atendente humano."""

    def escalar(self, conversa: Conversa, resumo: str, atributos: dict) -> None:
        """Transfere `conversa` pra um humano.

        `resumo` explica em uma frase por que a IA parou — e o que o
        atendente le antes de assumir. `atributos` carrega o que o sistema
        de atendimento precisa pra rotear o caso (fila, prioridade, idioma);
        vai vazio enquanto nao houver roteamento pra alimentar.

        A conversa ja chega aqui com o status atualizado: esta porta cuida
        do mundo externo, nao do estado do nucleo. Depois desta chamada a IA
        nao responde mais nessa conversa.
        """
        ...
