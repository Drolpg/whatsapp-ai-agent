"""Domain Services — regra de negocio que nao pertence a nenhuma entidade.

Quando uma regra envolve mais de um objeto do dominio, ou nao cabe
naturalmente dentro de uma Entity nem de um Value Object, ela vira um Domain
Service: um objeto sem estado proprio, que so expressa uma politica do
negocio.

`TriagemService` e esse caso. Ele recebe uma `Conversa` e uma resposta
candidata gerada pela IA e decide se ela resolve o atendimento ou se a
conversa deve ser escalada pra um humano (ex: a IA pediu escalar
explicitamente, ou o numero de tentativas sem sucesso passou do limite).
Repare no que ele *nao* faz: nao gera a resposta e nao sabe quem a gerou —
isso e problema de um `ProvedorLLM` la na infraestrutura. Ele so decide o
que fazer com ela.

TODO(Fase 1): implementar `TriagemService` retornando `ResultadoTriagem`,
testavel sem nenhum mock.
"""
