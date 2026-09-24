"""Monta o checklist do fluxo do escritório para cada publicação."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .banco import Banco
from .config import Config
from .fontes.advbox import FichaAdvbox, PlanilhaAdvbox
from .fontes.drive import ResultadoDrive
from .interpretador import InterpretacaoFalhou
from .modelos import Interpretacao, ItemChecklist, Prazo, Publicacao, Triagem
from .prazos import (
    Calendario,
    calcular_prazo_fatal,
    calcular_prazo_interno,
    data_publicacao,
    eh_justica_federal,
)
from .texto import normalizar_cpf, normalizar_processo

# Quando a IA falha ou não sabe classificar, usa-se o menor prazo usual (embargos)
# para a publicação aparecer no topo da fila.
PRAZO_SEGURANCA = 5


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


# ----------------------------------------------------------------------------- prazo
def calcular_prazo(pub: Publicacao, interp: Interpretacao | None, prov: dict, cfg: Config, hoje: date) -> Prazo | None:
    if interp and interp.prazo_dias_informado:
        dias, origem = interp.prazo_dias_informado, "publicacao"
    elif prov.get("prazo_padrao"):
        dias, origem = prov["prazo_padrao"], "padrao_do_escritorio"
    elif interp is None or interp.providencia == "outro" or interp.confianca == "baixa":
        dias, origem = PRAZO_SEGURANCA, "seguranca"
    else:
        return None  # ciência, audiência, implantação: sem prazo de peça

    contagem = (interp.contagem_informada if interp else None) or prov.get("contagem", "uteis")
    if interp and interp.rito == "administrativo" and not interp.contagem_informada:
        contagem = "corridos"

    cal = Calendario(eh_justica_federal(pub.tribunal, pub.orgao), cfg.feriados_extras)
    if contagem == "uteis":
        ciencia = pub.data_publicacao or data_publicacao(pub.data_disponibilizacao, cal)
    else:
        # Administrativo: sem data de ciência confiável, conta da disponibilização (mais cedo = mais seguro).
        ciencia = pub.data_publicacao or pub.data_disponibilizacao
    inicio, fatal = calcular_prazo_fatal(ciencia=ciencia, dias=dias, contagem=contagem, cal=cal)
    margem = prov.get("margem_interna", cfg.fluxos.get("margem_interna_padrao", 2))
    interno = calcular_prazo_interno(fatal, margem, hoje, cal)
    return Prazo(
        dias=dias,
        contagem=contagem,
        origem=origem,
        inicio_contagem=inicio,
        fatal=fatal,
        interno=interno,
        vencido=fatal < hoje,
        dias_uteis_ate_interno=cal.dias_uteis_entre(hoje, interno),
    )


# ----------------------------------------------------------------------------- senha
@dataclass
class AvaliacaoSenha:
    status: str
    detalhe: str


def avaliar_senha_govbr(testes: list[dict], tem_senha_advbox: bool, hoje: date, data_migracao: date, validade_dias: int) -> AvaliacaoSenha:
    """Decide o que fazer com a senha do Meu INSS a partir do histórico de testes."""
    como_obter = (
        "Orientar o cliente a obter nova senha: atendimento presencial na agência do INSS "
        "ou, se ele conseguir, recuperação pelo app gov.br (reconhecimento facial) / internet banking."
    )
    if not testes:
        if tem_senha_advbox:
            return AvaliacaoSenha(
                "pendente",
                f"Há senha na planilha antiga do Advbox, mas nenhum teste registrado desde a migração "
                f"({_br(data_migracao)}). TESTE no Meu INSS antes de pedir qualquer coisa ao cliente "
                "e registre o resultado no painel.",
            )
        return AvaliacaoSenha(
            "atencao",
            "Nenhuma senha na planilha do Advbox e nenhum teste registrado. Confirmar no Expedit se "
            f"há acesso cadastrado; se não houver: {como_obter}",
        )

    ultimo = testes[0]
    quando = date.fromisoformat(ultimo["testado_em"])
    por = f" por {ultimo['testado_por']}" if ultimo.get("testado_por") else ""
    if ultimo["resultado"] == "funcionou":
        idade = (hoje - quando).days
        if idade <= validade_dias:
            return AvaliacaoSenha("ok", f"Senha funcionou em {_br(quando)}{por}. Não precisa pedir ao cliente.")
        return AvaliacaoSenha("pendente", f"Último teste OK foi em {_br(quando)}{por} ({idade} dias). Testar de novo.")
    if ultimo["resultado"] == "nova_senha_agencia":
        return AvaliacaoSenha(
            "atencao",
            f"Cliente foi orientado a obter nova senha em {_br(quando)}{por}. Confirmar com ele se já obteve "
            "e testar a nova senha.",
        )
    falhas_seguidas = 0
    for t in testes:
        if t["resultado"] != "falhou":
            break
        falhas_seguidas += 1
    if falhas_seguidas >= 2:
        return AvaliacaoSenha(
            "atencao",
            f"A senha falhou {falhas_seguidas} vezes seguidas (último teste em {_br(quando)}{por}). "
            f"Não insista (risco de bloqueio). {como_obter}",
        )
    return AvaliacaoSenha(
        "atencao",
        f"A senha falhou em {_br(quando)}{por}. Testar mais uma vez conferindo CPF, senha e o código de "
        "verificação em duas etapas (vai para o celular do cliente). Se falhar de novo, pedir nova senha.",
    )


# ----------------------------------------------------------------------------- itens
def _item_sistema(pub: Publicacao, interp: Interpretacao | None) -> ItemChecklist:
    avisos = []
    if interp and interp.numero_processo and pub.numero_processo:
        if normalizar_processo(interp.numero_processo) != normalizar_processo(pub.numero_processo):
            avisos.append(
                f"o número no texto ({interp.numero_processo}) é diferente do cadastrado no Expedit ({pub.numero_processo})"
            )
    if pub.origem != "manual":  # texto colado à mão não tem cadastro para comparar
        if not pub.numero_processo:
            avisos.append("publicação sem processo vinculado no Expedit")
        if not pub.cliente_nome and not pub.cliente_cpf:
            avisos.append("publicação sem cliente vinculado no Expedit")
    detalhe = (
        f"Processo {pub.numero_processo or (interp.numero_processo if interp else None) or '—'} | Cliente {pub.cliente_nome or '—'} | "
        f"{pub.orgao or pub.tribunal or 'órgão não informado'}. Conferir se o processo está cadastrado "
        "e atualizado no Expedit (partes, benefício, fase)."
    )
    if avisos:
        detalhe += " ATENÇÃO: " + "; ".join(avisos) + "."
    return ItemChecklist(id="sistema", titulo="Confirmar informações no sistema (Expedit)", detalhe=detalhe,
                         status="atencao" if avisos else "pendente")


def _item_drive(res: ResultadoDrive | None, exigidos: list[str], catalogo: dict, mencionados: list[str]) -> ItemChecklist:
    nome = lambda k: catalogo.get(k, {}).get("nome", k)  # noqa: E731
    extra = f" A publicação menciona: {', '.join(mencionados)}." if mencionados else ""
    if not exigidos and not mencionados:
        return ItemChecklist(id="drive", titulo="Documentação no Drive", status="nao_se_aplica",
                             detalhe="Esta providência não exige documentos específicos.")
    if res is None:
        return ItemChecklist(id="drive", titulo="Verificar documentação no Drive", status="pendente",
                             detalhe="Drive não configurado no robô — conferir manualmente: "
                                     + ", ".join(nome(k) for k in exigidos) + "." + extra)
    if res.pasta is None:
        return ItemChecklist(id="drive", titulo="Verificar documentação no Drive", status="atencao",
                             detalhe="Pasta do cliente NÃO encontrada no Drive (busca por CPF e nome). "
                                     "Procurar manualmente antes de pedir documentos ao cliente." + extra)
    partes = [f"Pasta: {res.pasta} ({res.arquivos_total} arquivos)."]
    if res.encontrados:
        partes.append("Já existem: " + "; ".join(f"{nome(k)} ({', '.join(v[:2])})" for k, v in res.encontrados.items()) + ".")
    if res.faltando:
        partes.append("NÃO encontrados pelo nome do arquivo: " + ", ".join(nome(k) for k in res.faltando)
                      + ". Abrir a pasta e conferir (o arquivo pode ter outro nome) antes de pedir ao cliente.")
    return ItemChecklist(id="drive", titulo="Verificar documentação no Drive",
                         status="atencao" if res.faltando or mencionados else "ok",
                         detalhe=" ".join(partes) + extra)


def _item_advbox(ficha: FichaAdvbox | None, planilha_carregada: bool) -> ItemChecklist:
    titulo = "Consultar planilha do Advbox antes de ligar para o cliente"
    if not planilha_carregada:
        return ItemChecklist(id="advbox", titulo=titulo, status="pendente",
                             detalhe="Planilha do Advbox não configurada no robô — consultar manualmente.")
    if ficha is None:
        return ItemChecklist(id="advbox", titulo=titulo, status="atencao",
                             detalhe="Cliente não localizado na planilha do Advbox (CPF, processo e nome). "
                                     "Provavelmente é cliente novo, cadastrado só no Expedit.")
    rotulos = {"telefone": "Telefone", "email": "E-mail", "endereco": "Endereço", "beneficio": "Benefício",
               "nb": "NB", "der": "DER", "observacoes": "Obs."}
    dados = "; ".join(f"{rotulos[k]}: {v}" for k, v in ficha.dados.items() if k in rotulos)
    detalhe = f"Encontrado por {ficha.encontrado_por}. {dados}."
    if ficha.faltando:
        detalhe += " Faltam na planilha: " + ", ".join(ficha.faltando) + " — só isso justifica contatar o cliente."
        status = "atencao"
    else:
        detalhe += " Dados cadastrais completos: NÃO é preciso ligar para o cliente para obtê-los."
        status = "ok"
    return ItemChecklist(id="advbox", titulo=titulo, status=status, detalhe=detalhe)


def _item_peca(prov_chave: str, prov: dict, prazo: Prazo | None, interp: Interpretacao | None, erro: str | None) -> ItemChecklist:
    peca = prov.get("peca")
    if erro:
        return ItemChecklist(id="peca", titulo="Triagem manual obrigatória", status="atencao",
                             detalhe=f"O robô não conseguiu interpretar ({erro}). Leia a íntegra. "
                                     f"Prazo de segurança aplicado: {_br(prazo.interno) if prazo else '—'}.")
    partes = []
    if peca:
        partes.append(f"Peça: {peca}.")
    else:
        partes.append("Sem peça a elaborar.")
    if prazo:
        orig = {"publicacao": "prazo dado na publicação", "padrao_do_escritorio": "prazo legal padrão",
                "seguranca": "prazo de segurança — confirmar"}[prazo.origem]
        partes.append(
            f"Prazo: {prazo.dias} dias {'úteis' if prazo.contagem == 'uteis' else 'corridos'} ({orig}), "
            f"contando de {_br(prazo.inicio_contagem)}. FATAL: {_br(prazo.fatal)}. "
            f"INTERNO: {_br(prazo.interno)}."
        )
    if prov.get("orientacao"):
        partes.append(prov["orientacao"])
    if interp and interp.pontos_de_atencao:
        partes.append("Atenção: " + " | ".join(interp.pontos_de_atencao))
    if interp and interp.confianca != "alta":
        partes.append(f"Confiança da IA: {interp.confianca} — advogado deve confirmar a classificação.")
    status = "atencao" if (prazo and prazo.vencido) or (interp and interp.confianca == "baixa") or prov_chave == "outro" else "pendente"
    titulo = f"Elaborar {peca.lower()}" if peca else "Providência sem peça"
    return ItemChecklist(id="peca", titulo=titulo, status=status, detalhe=" ".join(partes))


# ----------------------------------------------------------------------------- orquestração
class Triador:
    def __init__(self, cfg: Config, banco: Banco, interpretador, advbox: PlanilhaAdvbox, drive):
        self.cfg, self.banco, self.interpretador, self.advbox, self.drive = cfg, banco, interpretador, advbox, drive

    def triar(self, pub: Publicacao, hoje: date | None = None) -> Triagem:
        hoje = hoje or date.today()
        interp, erro = None, None
        try:
            interp = self.interpretador.interpretar(pub)
        except InterpretacaoFalhou as e:
            erro = str(e)

        chave = interp.providencia if interp and interp.providencia in self.cfg.providencias else "outro"
        prov = self.cfg.providencias[chave]
        prazo = calcular_prazo(pub, interp, prov, self.cfg, hoje)

        itens = [_item_sistema(pub, interp)]
        # Etapa 1: só publicação + IA + prazo. Etapa 2 liga Drive, senha gov.br e planilha do Advbox.
        if self.cfg.etapa >= 2:
            itens += self._itens_integracoes(pub, interp, prov, hoje)
        itens.append(_item_peca(chave, prov, prazo, interp, erro))
        if prov.get("peca"):
            itens.append(ItemChecklist(
                id="protocolo", titulo="Revisão do advogado, protocolo e baixa no Expedit", status="pendente",
                detalhe=f"Protocolar até o prazo interno{' (' + _br(prazo.interno) + ')' if prazo else ''} "
                        "e registrar o protocolo no Expedit.",
            ))

        return Triagem(
            publicacao_id=pub.id,
            criada_em=datetime.now(),
            responsavel=pub.responsavel or prov.get("responsavel") or self.cfg.fluxos.get("responsavel_padrao", "triagem"),
            interpretacao=interp,
            erro_interpretacao=erro,
            providencia=chave,
            peca=prov.get("peca"),
            prazo=prazo,
            checklist=itens,
        )

    def _itens_integracoes(self, pub: Publicacao, interp: Interpretacao | None, prov: dict, hoje: date) -> list[ItemChecklist]:
        nome = pub.cliente_nome or (interp.cliente_nome if interp else None)
        processo = pub.numero_processo or (interp.numero_processo if interp else None)
        ficha = self.advbox.buscar(cpf=pub.cliente_cpf, processo=processo, nome=nome)
        cpf = pub.cliente_cpf or (normalizar_cpf(ficha.dados.get("cpf")) if ficha else None)

        catalogo = self.cfg.fluxos.get("documentos", {})
        exigidos = list(prov.get("documentos", []))
        res_drive = None
        if self.drive and exigidos:
            res_drive = self.drive.verificar(cpf=cpf, nome=nome, exigidos=exigidos, catalogo=catalogo)

        itens = [
            _item_drive(res_drive, exigidos, catalogo, interp.documentos_mencionados if interp else []),
        ]
        if prov.get("precisa_govbr"):
            if cpf:
                av = avaliar_senha_govbr(
                    self.banco.testes_senha(cpf), bool(ficha and ficha.tem_senha_govbr), hoje,
                    self.cfg.data_migracao, self.cfg.fluxos.get("senha_valida_por_dias", 30),
                )
                itens.append(ItemChecklist(id="senha_govbr", titulo="Senha gov.br / Meu INSS", status=av.status, detalhe=av.detalhe))
            else:
                itens.append(ItemChecklist(id="senha_govbr", titulo="Senha gov.br / Meu INSS", status="atencao",
                                           detalhe="CPF do cliente não encontrado no Expedit nem no Advbox — "
                                                   "cadastrar o CPF para controlar os testes de senha."))
        itens.append(_item_advbox(ficha, self.advbox.carregada))
        return itens

    def triar_pendentes(self, hoje: date | None = None) -> list[Triagem]:
        feitas = []
        for pub in self.banco.publicacoes_sem_triagem():
            t = self.triar(pub, hoje)
            self.banco.salvar_triagem(t)
            feitas.append(t)
        return feitas
