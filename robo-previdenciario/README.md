# Robô de triagem de publicações — escritório previdenciário

Todo dia o robô pega as publicações exportadas do **Expedit**. Uma IA (Claude, da Anthropic) lê cada uma e classifica a providência. Em seguida o robô monta, para o colaborador responsável, o **checklist do fluxo do escritório**, com a peça a elaborar, o **prazo fatal** e o **prazo interno**.

## O que o escritório pediu × o que o robô faz

| Pedido | Como o robô resolve |
|---|---|
| Puxar a publicação | Importa a exportação do Expedit (CSV/XLSX) sem duplicar o que já entrou. |
| Interpretar | A IA resume em linguagem simples, classifica a providência (réplica, laudo, recurso, exigência do INSS…), copia o trecho que manda agir e aponta riscos. |
| Confirmar informações no sistema | Compara o nº do processo do texto com o cadastro do Expedit e avisa se faltar cliente ou processo. |
| Ver se a documentação já está no Drive | Localiza a pasta do cliente (por CPF ou nome) e diz quais documentos **já existem** e quais não achou. |
| Ver se a senha realmente não está pegando / se é melhor pegar nova na agência | Registra o histórico de testes da senha gov.br (quem testou, quando, resultado). Pede novo teste quando a senha só existe na planilha antiga. Após 2 falhas seguidas, recomenda **nova senha na agência**. **A senha em si nunca é gravada nem exibida.** |
| Consultar a planilha do Advbox para não ligar à toa | Busca o cliente na planilha antiga (CPF → processo → nome). Mostra telefone, NB, benefício etc. e diz se **não é preciso ligar**. Lista só o que realmente falta. |
| Dizer a peça e o prazo (cumprir prazo interno) | Prazo **calculado pelo código, não pela IA**: dias úteis, recesso de 20/12 a 20/01, feriados nacionais e da Justiça Federal, e prazo interno com margem configurável. |

Tudo aparece num **painel web** (fila ordenada por prazo interno). Cada responsável também recebe um **e-mail diário**.

## Como funciona

```
Expedit (exportação) ──► importar ──► IA interpreta ──► cálculo de prazo
                                          │
      Planilha Advbox ◄── cruza dados ────┤
      Google Drive    ◄── confere docs ───┤
      Testes de senha ◄── histórico ──────┘
                                          ▼
                         Checklist no painel + e-mail diário
```

## Implantação por etapas

| Etapa | O que roda | Como ligar |
|---|---|---|
| **1 (atual)** | Baixa do **DJEN** pelas OABs do escritório → IA interpreta → peça, prazo fatal e prazo interno | `ROBO_ETAPA=1` (padrão) |
| 2 | + Google Drive, senha gov.br e planilha do Advbox | `ROBO_ETAPA=2` |

Baixar direto do DJEN (consulta pública do CNJ, sem login), já interpretando:

```bash
python -m robo.cli djen --oab 12345/PR --de 23/09/2026 --ate 24/09/2026 --interpretar
```

As OABs podem ficar fixas no `.env` (`DJEN_OABS=12345/PR,67890/SC`), e aí basta `python -m robo.cli djen --interpretar`.
Sem `--de`, o robô busca os últimos 3 dias, para cobrir fim de semana. Publicação já baixada não entra em dobro.
A resposta original do DJEN fica salva em `dados/djen_ultima_resposta.json`, para conferência.

Para testar uma publicação avulsa, sem DJEN nem Expedit: salve o texto de uma publicação num arquivo `.txt` e rode

```bash
python -m robo.cli interpretar publicacao.txt --disponibilizacao 24/09/2026 --tribunal TRF4
```

## Uso em vários computadores

O robô roda em **um único lugar** e todo mundo acessa o painel pelo navegador (Chrome, Edge), sem instalar nada em cada máquina:

- **Opção simples:** um computador do escritório que fique sempre ligado roda o robô e o painel. Os outros abrem `http://IP-DESSE-PC:8000` na rede interna.
- **Opção recomendada para acesso de fora do escritório:** um servidor pequeno na nuvem (por exemplo Google Cloud, AWS ou uma VPS brasileira, a partir de ~R$ 50/mês), com login e HTTPS. Nesse caso, o painel precisa de login por colaborador antes de ir para a internet.

## Instalação (uma vez)

Requer Python 3.11 ou mais novo.

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # e preencha
```

Ajuste depois:

1. **`config/planilhas.yaml`**: nomes das colunas da exportação do Expedit e da planilha do Advbox.
2. **`config/fluxos.yaml`**: tipos de providência, prazos padrão, margem interna, documentos exigidos e **data da migração Advbox → Expedit**. Dá para editar sem programar.
3. **`config/feriados_locais.yaml`**: feriados municipais e suspensões de expediente do tribunal.

## Uso diário

```bash
python -m robo.cli rodar-dia exportacao_expedit.xlsx --enviar   # importa, tria e manda os e-mails
python -m robo.cli painel --host 0.0.0.0                        # painel em http://IP-DO-PC:8000
```

Para rodar sozinho todo dia, use o Agendador de Tarefas do Windows ou o cron do Linux, por exemplo às 7h.

No painel, o colaborador:
- abre a publicação e marca cada passo do checklist; fica registrado quem marcou;
- registra o teste da senha (✅ funcionou / ❌ falhou / 🏢 orientei nova senha);
- **reclassifica** se a IA errou, e o prazo é recalculado;
- conclui a publicação.

Para testar com dados fictícios: `python -m robo.cli importar exemplos/expedit_exemplo.csv`.

## Limites e cuidados

- **O prazo fatal deve ser conferido pelo advogado.** O robô considera publicado no 1º dia útil após a disponibilização no DJEN e usa o calendário federal quando o órgão é TRF, JEF ou Vara Federal. Portarias locais de suspensão entram em `feriados_locais.yaml`.
- Quando a IA falha ou fica em dúvida, a publicação vai para **triagem manual**, com um *prazo de segurança* de 5 dias úteis para subir na fila.
- O teste da senha no Meu INSS continua **humano**: o gov.br tem captcha e verificação em duas etapas, e automatizar esse login é frágil e arriscado.
- **LGPD**: o texto das publicações é enviado à API da Anthropic para interpretação. Formalize isso na política de privacidade e no contrato com o cliente. Os dados ficam num arquivo SQLite local (`dados/robo.db`); faça backup. O painel tem senha, mas deve ficar só na rede interna ou atrás de VPN.
- O Expedit não tem API pública documentada. Se o fornecedor liberar API ou webhook, implemente `robo/fontes/expedit.py::ExpeditAPI` para eliminar a exportação manual.

## Próximos passos sugeridos

1. Pedir ao Expedit acesso por API ou webhook, para não precisar exportar.
2. Enviar o resumo diário por WhatsApp, além do e-mail.
3. Gerar a **minuta da peça** a partir dos modelos do escritório, usando o resumo e os dados já cruzados.
4. Relatório semanal de produtividade: prazos cumpridos antes do interno, publicações por responsável.

## Desenvolvimento

```bash
pip install -r requirements-dev.txt
python -m pytest
```
