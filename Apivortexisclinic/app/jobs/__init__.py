"""
Rotinas que rodam FORA de uma requisição.

São comandos, não endpoints, e é de propósito: nada aqui deve depender de
alguém estar com a tela aberta. Rode com o agendador do sistema
(Agendador de Tarefas no Windows, cron no Linux):

    python -m app.jobs.emails          # entrega a fila de e-mail
    python -m app.jobs.lembretes       # enfileira os lembretes do dia

Os dois são **idempotentes**: rodar duas vezes não manda nada duas vezes.
A fila tem chave de deduplicação para isso.
"""
