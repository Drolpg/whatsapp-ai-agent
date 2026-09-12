"""Testes do nucleo de decisao — os mais baratos da suite.

Como `core/` e Python puro, estes testes constroem os objetos direto e
verificam comportamento: as regras do `TriagemService`, o que a `Conversa`
permite e o que ela recusa, e o fluxo de `processar_mensagem_recebida` com
implementacoes falsas (em memoria) das portas. Nenhuma rede, nenhum
arquivo, nenhum Docker.

TODO(Fase 1): cobrir `Conversa`, `Mensagem` e os tres casos de triagem do
criterio de aceite — resolvido sem escalar, escalado por pedido explicito
da IA, escalado por numero de tentativas.
TODO(Fase 2): cobrir `processar_mensagem_recebida` ponta a ponta com
adapters falsos.
"""
