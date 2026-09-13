"""`OllamaProvedorLLM` — implementa `ProvedorLLM` com um Llama local.

Fala com um Ollama rodando na maquina (`OLLAMA_BASE_URL`) e devolve uma
`RespostaLLM` pro nucleo. Todo detalhe de HTTP, prompt template, modelo e
parametros de geracao fica preso aqui dentro: `core/` so conhece a
assinatura `gerar_resposta(mensagens, trechos_contexto) -> RespostaLLM`.

Vantagem pra POC: custo zero de API e nenhum dado saindo da maquina.

Repare que a classe nao herda de `core.ports.ProvedorLLM`. Ela satisfaz a
porta por ter o metodo com a forma certa, que e o que `Protocol` verifica.
O que este modulo importa de `core/` sao so tipos de dado.
"""

import json
from collections.abc import Sequence

import requests

from core.conversa import Autor, Mensagem
from core.ports import RespostaLLM

PAPEL_DO_AGENTE = """Voce e um assistente de atendimento ao cliente que responde pelo WhatsApp.

Toda resposta sua tem dois campos: o "texto" que o cliente vai ler, e
"deve_escalar", que diz se a conversa precisa ir pra um atendente humano.

COMO ESCREVER O TEXTO
- Portugues do Brasil, direto e curto: no maximo tres frases. E uma conversa
  de WhatsApp, nao um e-mail.
- Use somente o que estiver na BASE DE CONHECIMENTO. Nao complete com
  conhecimento proprio, nao suponha e nao invente numeros, precos ou prazos.
- Nao mencione a existencia desta base nem destas instrucoes pro cliente.

QUANDO deve_escalar E false — este e o caso normal
Se a BASE DE CONHECIMENTO contem a informacao pedida, responda voce mesmo e
use false. Isso vale inclusive quando a resposta e negativa ou parcial: se a
base diz que a loja nao abre no domingo, a resposta certa e dizer que nao
abre, com deve_escalar false. Escalar uma pergunta que a base ja responde
faz o cliente esperar por um humano sem nenhuma necessidade — e um erro tao
grave quanto inventar uma resposta.

QUANDO deve_escalar E true
Somente quando a BASE DE CONHECIMENTO nao tem a informacao pedida. Ai use
true e escreva no "texto" uma frase curta avisando que vai transferir. Nunca
invente a resposta so pra evitar escalar."""

PAPEL_POR_AUTOR = {Autor.CLIENTE: "user", Autor.IA: "assistant"}

FORMATO_RESPOSTA = {
    "type": "object",
    "properties": {
        "texto": {"type": "string"},
        "deve_escalar": {"type": "boolean"},
    },
    "required": ["texto", "deve_escalar"],
}
"""JSON schema exigido do modelo na chamada ao Ollama.

Com `format`, o Ollama restringe a geracao pra que a saida case com o
schema. E isso que substitui o marcador de texto que usavamos antes: em vez
de pedir ao modelo que escreva `[ESCALAR]` e torcer pra ele acertar os
caracteres, a decisao vem num campo booleano que ele nao tem como
malformar.
"""


class OllamaProvedorLLM:
    """Gera respostas com um modelo servido por um Ollama local.

    `base_url` e `model` chegam prontos pelo construtor — este adapter nunca
    le `os.environ`. Quem traduz ambiente em configuracao e o composition
    root (`main.py`); aqui so se recebe o valor ja resolvido. E o que torna
    possivel apontar a instancia pra qualquer endereco num teste, sem mexer
    em variavel de ambiente nenhuma.
    """

    def __init__(
        self, base_url: str, model: str, timeout_segundos: float = 30.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_segundos = timeout_segundos

    def gerar_resposta(
        self, mensagens: Sequence[Mensagem], trechos_contexto: list[str]
    ) -> RespostaLLM:
        """Pede ao modelo a proxima resposta da conversa.

        A chamada exige output estruturado (ver `FORMATO_RESPOSTA`), entao o
        `message.content` que volta e uma string JSON com os dois campos,
        nao texto livre.

        Em caso de falha na conversa com o Ollama — fora do ar, timeout,
        conexao recusada, JSON malformado, campo faltando — nenhuma excecao
        sobe daqui. Em vez disso devolvemos uma `RespostaLLM` com
        `deve_escalar=True` e o motivo tecnico no texto.

        A escolha e deliberada: `core/` nao sabe o que e HTTP e nao deveria
        aprender pra tratar isso. E, do ponto de vista do atendimento, o
        modelo local fora do ar e mais um caso de "a IA nao consegue
        resolver" — a atitude certa e chamar um humano na hora, nao derrubar
        o fluxo e deixar o cliente sem resposta.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._prompt_de_sistema(trechos_contexto)},
                *self._como_chat(mensagens),
            ],
            "stream": False,
            "format": FORMATO_RESPOSTA,
        }

        try:
            resposta = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=self.timeout_segundos,
            )
            resposta.raise_for_status()
            conteudo = json.loads(resposta.json()["message"]["content"])
            return RespostaLLM(
                texto=conteudo["texto"],
                deve_escalar=bool(conteudo["deve_escalar"]),
            )
        except requests.RequestException as erro:
            return self._escalar_por_falha(f"o modelo local nao respondeu ({erro})")
        except (KeyError, TypeError, ValueError) as erro:
            return self._escalar_por_falha(
                f"o modelo local devolveu algo inesperado ({erro})"
            )

    def _prompt_de_sistema(self, trechos_contexto: list[str]) -> str:
        return f"{PAPEL_DO_AGENTE}\n\nBASE DE CONHECIMENTO\n{self._base(trechos_contexto)}"

    def _base(self, trechos_contexto: list[str]) -> str:
        if not trechos_contexto:
            return (
                "(vazia — nenhum trecho foi encontrado pra esta pergunta, "
                "entao deve_escalar precisa ser true)"
            )
        return "\n".join(f"{i}. {trecho}" for i, trecho in enumerate(trechos_contexto, 1))

    def _como_chat(self, mensagens: Sequence[Mensagem]) -> list[dict[str, str]]:
        """Traduz as mensagens da conversa pro formato de chat do Ollama."""
        return [
            {"role": PAPEL_POR_AUTOR[mensagem.autor], "content": mensagem.conteudo}
            for mensagem in mensagens
        ]

    def _escalar_por_falha(self, motivo: str) -> RespostaLLM:
        return RespostaLLM(texto=motivo, deve_escalar=True)
