"""`TACCanal` — implementa `Canal` via Twilio Agent Connect.

Entrada e saida do WhatsApp: recebe as mensagens do cliente pelo webhook do
TAC, converte o payload do Twilio nos termos do projeto e entrega pro fluxo
de triagem; na volta, envia o texto da resposta pelo mesmo canal.

E o unico lugar do sistema que conhece `TWILIO_ACCOUNT_SID`,
`TWILIO_CONVERSATION_CONFIGURATION_ID` e o formato de webhook do Twilio.
A licao da Fase 5 e essa: conectar um sistema externo real sem deixar que
ele vaze pro nucleo de decisao.

TODO(Fase 5): implementar o adapter e o servidor que expoe o webhook, ate a
primeira mensagem real ir e voltar pelo WhatsApp (Sandbox ou numero real).
"""
