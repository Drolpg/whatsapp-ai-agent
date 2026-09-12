"""Entidades do dominio — objetos com identidade propria.

Uma Entity e definida pela sua identidade, nao pelos seus valores: duas
`Conversa` com o mesmo conteudo mas `conversa_id` diferente sao conversas
diferentes, e uma `Conversa` continua sendo a mesma ao longo do tempo mesmo
que suas mensagens e seu status mudem.

`Conversa` e o **aggregate root** deste modelo: e o unico ponto de entrada
pra mudar o estado de uma conversa. Nada altera uma `Mensagem` da lista nem
o `status` por fora dela — quem quiser mudar algo pede pra `Conversa`. Isso
concentra as invariantes (ex: "nao se adiciona mensagem numa conversa
encerrada") em um lugar so.

TODO(Fase 1): implementar `Conversa` (conversa_id, mensagens, status entre
ATIVA / ESCALADA / ENCERRADA) com testes unitarios sem I/O e sem mock.
"""
