"""`TACCanalConversa` — implementa `CanalConversa` via Twilio Agent Connect.

Adapter de entrada e saida do WhatsApp: recebe as mensagens do cliente pelo
webhook do TAC, converte o payload do Twilio em termos do dominio e entrega
pro caso de uso; na volta, envia o texto da resposta pelo mesmo canal.

E o unico lugar do sistema que conhece `TWILIO_ACCOUNT_SID`,
`TWILIO_CONVERSATION_CONFIGURATION_ID` e o formato de webhook do Twilio.
A licao da Fase 5 e essa: conectar um sistema externo real sem deixar que
ele vaze pra dentro do dominio.

TODO(Fase 5): implementar o adapter e o servidor que expoe o webhook, ate a
primeira mensagem real ir e voltar pelo WhatsApp (Sandbox ou numero real).
"""
