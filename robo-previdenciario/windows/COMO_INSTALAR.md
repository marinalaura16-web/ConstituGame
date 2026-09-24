# Como instalar o robô no computador do escritório

Escolha **um** computador com Windows 10 ou 11 que fique ligado no horário de expediente. Só ele precisa do robô; os outros acessam o painel pelo navegador.

## 1. Baixar o robô (uma vez)
1. No GitHub, abra o repositório **ConstituGame** e selecione a branch **claude/automacao-fluxo-previdenciario-mt1x8k**.
2. Clique em **Code → Download ZIP**.
3. Extraia o ZIP e mova a pasta **robo-previdenciario** para `C:\RoboPrevidenciario`.

## 2. Instalar (uma vez)
1. Abra `C:\RoboPrevidenciario\windows` e dê **dois cliques** em **1_instalar.bat**.
   - Se o Windows avisar "O Windows protegeu o computador", clique em **Mais informações → Executar assim mesmo**.
   - Se o Python não estiver instalado, o próprio arquivo instala. Depois, rode **1_instalar.bat** de novo.
2. O Bloco de Notas vai abrir com o arquivo de configuração. Preencha:
   - `DJEN_OABS=` com as OABs do escritório, separadas por vírgula, por exemplo `DJEN_OABS=12345/PR,67890/SC`.
   - `ANTHROPIC_API_KEY=` com a chave da IA, criada em console.anthropic.com → API Keys.
   - `PAINEL_SENHA=` com uma senha para o painel.
3. Salve (Ctrl+S) e feche.

## 3. Usar
| Arquivo | O que faz |
|---|---|
| **2_buscar_publicacoes.bat** | Busca no DJEN as publicações dos últimos 3 dias. A IA indica a peça e o robô calcula o prazo fatal e o interno. O resultado abre no Bloco de Notas e fica salvo na pasta `dados`. |
| **3_abrir_painel.bat** | Liga o painel. Nos outros computadores, abra o endereço que aparece na janela, por exemplo `http://192.168.0.10:8000`. |
| **4_agendar_todo_dia.bat** | Faz o robô buscar sozinho, de segunda a sexta, no horário escolhido. |

## Se der erro
Tire um print da janela preta e envie para o Claude.
