"""Adapters da porta `CanalConversa` — por onde as mensagens entram e saem.

Isolam o canal real (WhatsApp via Twilio Agent Connect) do resto do sistema:
webhooks, payloads, identificadores do Twilio e formato de mensagem sao
traduzidos aqui pros termos do dominio (`Conversa`, `Mensagem`).

    tac_channel.py  Twilio Agent Connect  (Fase 5)
"""
