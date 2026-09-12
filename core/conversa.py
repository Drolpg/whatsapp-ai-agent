"""Os dados de uma conversa: `Conversa` e `Mensagem`.

`Mensagem` e um item simples e imutavel: quem enviou (`CLIENTE` ou `IA`), o
conteudo e o timestamp. Depois de criada, nao muda.

`Conversa` guarda um id, a lista de mensagens e um status (`ATIVA`,
`ESCALADA` ou `ENCERRADA`). E o unico jeito de mudar o estado de uma
conversa — quem quiser acrescentar uma mensagem ou marcar como escalada
pede pra ela, em vez de mexer na lista ou no status por fora. Isso mantem
num lugar so as regras do tipo "nao se adiciona mensagem numa conversa
encerrada".

TODO(Fase 1): implementar `Mensagem` e `Conversa`, com testes unitarios sem
I/O e sem mock.
"""
