"""`StudioGatewayHandoff` — implementa `GatewayHandoff` via Twilio Studio.

Traduz a decisao "escalar esta conversa" na sequencia concreta do Twilio:
dispara o Studio Flow de handoff (`create_studio_handoff_tool`), que cria a
Task no TaskRouter com o resumo e os atributos da conversa, ate ela chegar
na fila do atendente no Flex.

Este e o unico modulo do sistema que sabe disso. Pro `TriagemService` e pro
`processar_mensagem_recebida`, escalar continua sendo uma unica chamada sem
detalhe nenhum de Twilio.

TODO(Fase 6): implementar o adapter e validar ponta a ponta — mensagem, IA
nao resolve, Task aparece no Flex com o resumo.
"""
