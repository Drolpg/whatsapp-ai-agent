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
from dataclasses import dataclass
from typing import Protocol

from core.conversa import Conversa, Mensagem


@dataclass(frozen=True)
class RespostaLLM:
    """O que a IA devolve: o texto, e se ela acha que precisa de ajuda.

    Sao duas informacoes independentes, e manter as duas separadas e o
    ponto. Ja tentamos embutir o pedido de escalonamento dentro do proprio
    texto, como um marcador combinado — e o modelo corrompia o marcador
    (`[NESCALAR]`, `[NAO SEGUIR]`), fazendo o pedido se perder e o texto
    corrompido ir pro cliente. Um campo booleano nao tem como ser digitado
    errado.

    `texto` e o que iria pro cliente. Quando `deve_escalar` e verdadeiro
    ele geralmente e descartado — o que a IA rascunhou sem ter a informacao
    nao serve nem pro cliente nem pro atendente.
    """

    texto: str
    deve_escalar: bool


class ProvedorLLM(Protocol):
    """Quem transforma a conversa ate aqui em uma resposta candidata."""

    def gerar_resposta(
        self, mensagens: Sequence[Mensagem], trechos_contexto: list[str]
    ) -> RespostaLLM:
        """Gera a proxima resposta da IA.

        Recebe o historico da conversa (a ultima mensagem e a pergunta que
        precisa ser respondida) e os trechos de apoio ja recuperados.

        Devolve uma `RespostaLLM`: o texto pro cliente e, em campo separado,
        se o modelo se considera incapaz de responder com o que recebeu. A
        implementacao decide sozinha como montar o prompt, que modelo usar e
        como arrancar dele uma resposta nesse formato — o nucleo so espera
        que o campo `deve_escalar` seja confiavel, porque e nele que a
        triagem manda a conversa pra um humano.
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


class RepositorioConversas(Protocol):
    """Onde o estado de uma `Conversa` sobrevive entre uma mensagem e outra.

    Cada mensagem do cliente chega numa requisicao HTTP separada, entao o
    agente precisa reencontrar a conversa de antes: o historico, o status, e
    o motivo de um escalonamento. Guardar isso num dicionario de processo
    parecia suficiente ate deixar de ser — reiniciar o servidor apagava tudo,
    e com mais de um worker cada um teria a sua propria versao da mesma
    conversa, fazendo o limite de tentativas contar errado.

    Esta porta nao diz onde guardar. Uma implementacao pode usar memoria (bom
    pra teste), outra pode devolver ao canal aquilo que ele ja sabe. O nucleo
    so precisa de duas coisas: recuperar e salvar.
    """

    def obter_ou_criar(self, conversa_id: str) -> Conversa:
        """Devolve a conversa de `conversa_id`, ou uma nova se nao existir.

        A conversa volta como estava: mesmo historico, mesmo status. Uma que
        havia sido escalada volta escalada — e por isso que a implementacao
        reconstitui o estado em vez de reaplicar as transicoes.
        """
        ...

    def salvar(self, conversa: Conversa) -> None:
        """Guarda o estado atual, pra proxima mensagem encontrar.

        Chamado depois de processar cada mensagem. O que precisa sobreviver e
        o que nao da pra deduzir de novo: o status e o motivo do
        escalonamento. O historico, dependendo de onde se guarda, o proprio
        canal ja preserva.
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
