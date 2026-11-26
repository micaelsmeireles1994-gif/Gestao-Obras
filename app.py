import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import calendar
import base64
import os
import re
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão LSM", page_icon="🗼", layout="centered")
st.session_state.setdefault("ciclo", 0)
st.session_state.setdefault("aviso", "")
st.session_state.setdefault("usr_nome", "")
st.session_state.setdefault("usr_perfil", "")
st.session_state.setdefault("setor", "🗼 Rede Móvel")

def aplicar_fundo_marca_agua():
    img_path = None
    preferidos = ["fundo.jpg", "fundo.jpeg", "fundo.png", "fundo.webp"]
    ficheiros_pasta = os.listdir(".")
    mapa_lower = {f.lower(): f for f in ficheiros_pasta if os.path.isfile(f)}
    for p in preferidos:
        if p in mapa_lower:
            img_path = mapa_lower[p]
            break
    if not img_path:
        for f_low, f_real in mapa_lower.items():
            if f_low.endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_path = f_real
                break

    if img_path and os.path.exists(img_path):
        with open(img_path, "rb") as f:
            b64_img = base64.b64encode(f.read()).decode("utf-8")
        ext = "png" if img_path.lower().endswith(".png") else "jpeg"
        st.markdown(
            f"""
            <style>
            .stApp, [data-testid="stAppViewContainer"] {{
                background: linear-gradient(rgba(255, 255, 255, 0.82), rgba(255, 255, 255, 0.82)),
                            url("data:image/{ext};base64,{b64_img}") !important;
                background-size: cover !important;
                background-position: center top !important;
                background-attachment: fixed !important;
                background-repeat: no-repeat !important;
            }}
            [data-testid="stHeader"] {{
                background: transparent !important;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

aplicar_fundo_marca_agua()

MESES = {
    1: "01 - Janeiro", 2: "02 - Fevereiro", 3: "03 - Março", 4: "04 - Abril",
    5: "05 - Maio", 6: "06 - Junho", 7: "07 - Julho", 8: "08 - Agosto",
    9: "09 - Setembro", 10: "10 - Outubro", 11: "11 - Novembro", 12: "12 - Dezembro"
}

ESTADOS_OBRA = ["Nova", "Execução", "Parcial", "Concluída"]

def extrair_id_drive(url):
    m = re.search(r"/d/([a-zA-Z0-9_-]+)", str(url))
    return m.group(1) if m else ""

def separar_links_fotos(texto_fotos):
    if not texto_fotos:
        return []
    partes = [p.strip() for p in str(texto_fotos).replace("\n", "|").split("|")]
    return [p for p in partes if p.startswith("http")]

def mostrar_anexos_obra(obra_id, nome_obra, url_pdf, texto_fotos):
    url_limpo = str(url_pdf).strip()
    lista_fotos = separar_links_fotos(texto_fotos)

    if url_limpo.startswith("http"):
        fid = extrair_id_drive(url_limpo)
        st.markdown(f"**📎 Documento / Projeto da Obra ({obra_id})**")
        b1, b2 = st.columns(2)
        b1.link_button("📄 Abrir PDF noutra aba", url_limpo, type="primary", use_container_width=True)
        if fid:
            b2.link_button("📥 Descarregar PDF", f"https://drive.google.com/uc?export=download&id={fid}", use_container_width=True)
            with st.expander("👁️ Consultar PDF diretamente aqui na aplicação"):
                components.iframe(f"https://drive.google.com/file/d/{fid}/preview", height=520, scrolling=True)
    else:
        st.caption(f"ℹ️ A obra {obra_id} ({nome_obra}) não tem ficheiro PDF anexado.")

    if lista_fotos:
        with st.expander(f"🖼️ Ver Fotografias da Obra ({len(lista_fotos)} foto(s))", expanded=False):
            cols_f = st.columns(2)
            for idx, link_f in enumerate(lista_fotos):
                fid_f = extrair_id_drive(link_f)
                with cols_f[idx % 2]:
                    if fid_f:
                        st.image(f"https://drive.google.com/thumbnail?id={fid_f}&sz=w800", caption=f"Foto {idx + 1}", use_container_width=True)
                    st.link_button(f"🔍 Abrir Foto {idx + 1}", link_f, use_container_width=True)
    else:
        st.caption("📷 Sem fotografias associadas a esta obra.")

def normalizar_estado(valor):
    v = str(valor).strip().lower()
    if v in ["execucao", "execuçao", "execução", "em curso", "em execucao", "em execução"]:
        return "Execução"
    if v in ["concluida", "concluída", "fechada", "terminada"]:
        return "Concluída"
    if v == "parcial":
        return "Parcial"
    if v == "nova" or v == "":
        return "Nova"
    return str(valor).strip()

def obter_config_setor(setor_escolhido):
    if "Eletricidade" in setor_escolhido:
        return {
            "titulo": "⚡ Eletricidade LSM",
            "pdf_cab": "ELETRICIDADE LSM",
            "pdf_tag": "Eletricidade_LSM",
            "secret_key": "apps_script_url_eletricidade"
        }
    return {
        "titulo": "🗼 Rede Móvel LSM",
        "pdf_cab": "REDE MOVEL LSM",
        "pdf_tag": "RedeMovel_LSM",
        "secret_key": "apps_script_url"
    }

def txt_pdf(valor, limite=40):
    return str(valor)[:limite].encode("latin-1", "replace").decode("latin-1")

def bytes_pdf(doc):
    out = doc.output()
    return out.encode("latin-1") if isinstance(out, str) else bytes(out)

def ajustar_colunas(df, sinonimos):
    if df.empty:
        return df
    mapa = {str(c).strip().lower(): c for c in df.columns}
    trocas = {}
    for destino, opcoes in sinonimos.items():
        if destino not in df.columns:
            for op in opcoes:
                if op.lower() in mapa:
                    trocas[mapa[op.lower()]] = destino
                    break
    return df.rename(columns=trocas) if trocas else df

@st.cache_data(ttl=15)
def ler_servidor(url_script):
    r = requests.get(url_script, timeout=15)
    r.raise_for_status()
    pacote = r.json()

    def extrair(aba, cols, sin=None, pos_fallback=True, max_pos=None):
        df = pd.DataFrame(pacote.get(aba, []))
        if df.empty:
            return pd.DataFrame(columns=cols)
        if sin:
            df = ajustar_colunas(df, sin)
        cols_orig = list(df.columns)
        limite_pos = len(cols) if max_pos is None else max_pos
        for i, c in enumerate(cols):
            if c not in df.columns:
                if pos_fallback and i < limite_pos and i < len(cols_orig) and cols_orig[i] not in cols:
                    df[c] = df[cols_orig[i]]
                else:
                    df[c] = ""
        return df[cols]

    obras = extrair(
        "Obras",
        ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"],
        {
            "ID Obra": ["ID", "Codigo", "Código", "Obra ID", "Ref"],
            "Nome da Obra": ["Obra", "Nome", "Designacao", "Designação", "Local"],
            "Cliente": ["Clientes", "Entidade"],
            "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento", "Adjudicado", "Valor Obra"],
            "PDF": ["Link PDF", "Ficheiro", "Projeto", "Anexo", "URL"],
            "Fotos": ["Foto", "Fotografias", "Imagens", "Links Fotos"]
        },
        pos_fallback=True,
        max_pos=7
    )
    elem_raw = extrair(
        "Elementos",
        ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"],
        {
            "Elemento": ["Colaborador", "Colaboradores", "Nome", "Trabalhador", "Tecnico", "Técnico"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"]
        },
        pos_fallback=False
    )
    cols_e_orig = list(pd.DataFrame(pacote.get("Elementos", [])).columns)
    if "Elemento" not in elem_raw.columns or (elem_raw["Elemento"].astype(str).str.strip() == "").all():
        if len(cols_e_orig) >= 1 and cols_e_orig[0] not in ["Utilizador", "Senha", "Perfil"]:
            df_tmp = pd.DataFrame(pacote.get("Elementos", []))
            elem_raw["Elemento"] = df_tmp[cols_e_orig[0]]
            if len(cols_e_orig) >= 2 and cols_e_orig[1] not in ["Utilizador", "Senha", "Perfil"]:
                elem_raw["Valor_Dia"] = df_tmp[cols_e_orig[1]]

    elem = elem_raw[["Elemento", "Valor_Dia"]].copy()
    users = elem_raw[["Utilizador", "Senha", "Perfil"]].copy()

    meios = extrair(
        "Meios",
        ["Meio / Equipamento", "Valor_Dia"],
        {
            "Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento", "Matricula", "Matrícula", "Nome"],
            "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Custo Dia", "Preco", "Preço", "Valor"]
        }
    )
    mat = extrair(
        "Materiais",
        ["Material", "Unidade", "Preco_Unitario"],
        {
            "Material": ["Nome", "Artigo", "Descricao", "Descrição", "Produto"],
            "Unidade": ["Un", "Un.", "Medida", "Unid"],
            "Preco_Unitario": ["Preco Unitario", "Preço Unitário", "Preco", "Preço", "Valor", "Valor_Unitario", "Custo"]
        }
    )
    diario = extrair(
        "Registos_Diarios",
        ["ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
         "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas", "Dias Falta"],
        {"Elemento": ["Colaborador"], "Meio": ["Viatura"], "Dias Falta": ["Faltas", "Falta"]},
        pos_fallback=True,
        max_pos=14
    )
    return obras, elem, users, meios, mat, diario

def guardar_aba(url_script, aba, df):
    limpo = df.fillna("")
    linhas = [limpo.columns.tolist()] + limpo.values.tolist()
    r = requests.post(
        url_script,
        data=json.dumps({"sheet": aba, "rows": linhas}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=25
    )
    r.raise_for_status()

def enviar_ficheiro_drive(url_script, nome_fich, bytes_fich, mime_type="application/pdf"):
    b64 = base64.b64encode(bytes_fich).decode("utf-8")
    r = requests.post(
        url_script,
        data=json.dumps({
            "action": "upload_pdf",
            "filename": nome_fich,
            "mime": mime_type,
            "base64": b64
        }),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=45
    )
    r.raise_for_status()
    resp = r.json()
    if "url" not in resp:
        raise ValueError(resp.get("error", "O Apps Script não devolveu o link do ficheiro."))
    return resp["url"]

def adicionar_fotos_obra(df_o, id_obra, lista_ficheiros, url_script):
    atuais = []
    if not df_o[df_o["ID Obra"] == id_obra].empty:
        atuais = separar_links_fotos(df_o.loc[df_o["ID Obra"] == id_obra, "Fotos"].iloc[0])
    novos = []
    for f in lista_ficheiros:
        mime = f.type if getattr(f, "type", "") else "image/jpeg"
        nome_f = f"FOTO_{id_obra}_{f.name}"
        url_f = enviar_ficheiro_drive(url_script, nome_f, f.getvalue(), mime_type=mime)
        novos.append(url_f)
    todos = atuais + novos
    df_o.loc[df_o["ID Obra"] == id_obra, "Fotos"] = " | ".join(todos)
    return len(novos)

def guardar_elementos_e_users(url_script, df_e, df_u):
    e_limpo = df_e[df_e["Elemento"].fillna("").astype(str).str.strip() != ""][["Elemento", "Valor_Dia"]].reset_index(drop=True)
    u_limpo = df_u[df_u["Utilizador"].fillna("").astype(str).str.strip() != ""][["Utilizador", "Senha", "Perfil"]].reset_index(drop=True)
    u_limpo["Perfil"] = u_limpo["Perfil"].fillna("").astype(str).str.strip()
    u_limpo.loc[u_limpo["Perfil"] == "", "Perfil"] = "Admin"
    u_limpo.loc[u_limpo["Utilizador"].str.lower() == "admin", "Perfil"] = "Admin"
    combinado = pd.concat([e_limpo, u_limpo], axis=1).fillna("")
    for col in ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]:
        if col not in combinado.columns:
            combinado[col] = ""
    guardar_aba(url_script, "Elementos", combinado[["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]])

def recalcular_obras(url_script, df_o, df_d):
    o = df_o.copy()
    o["ID Obra"] = o["ID Obra"].fillna("").astype(str).str.strip()
    o["Nome da Obra"] = o["Nome da Obra"].fillna("").astype(str).str.strip()
    o["Estado"] = o["Estado"].apply(normalizar_estado)
    for col_extra in ["PDF", "Fotos"]:
        if col_extra not in o.columns:
            o[col_extra] = ""
        o[col_extra] = o[col_extra].fillna("").astype(str).str.strip()
    sem_id = (o["ID Obra"] == "") & (o["Nome da Obra"] != "")
    if sem_id.any():
        o.loc[sem_id, "ID Obra"] = [f"OB-{idx+1:02d}" for idx in o[sem_id].index]
    o["Valor Adjudicado"] = pd.to_numeric(o["Valor Adjudicado"], errors="coerce").fillna(0.0)
    gastos = {}
    if not df_d.empty:
        d = df_d.copy()
        d["ID Obra"] = d["ID Obra"].fillna("").astype(str).str.strip()
        d["Total do Dia"] = pd.to_numeric(d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos = d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    o["Total Gasto"] = o["ID Obra"].map(gastos).fillna(0.0)
    o["Saldo Restante"] = o["Valor Adjudicado"] - o["Total Gasto"]
    cols_ordem = ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"]
    guardar_aba(url_script, "Obras", o[cols_ordem])

def converter_datas(serie):
    s = serie.fillna("").astype(str).str.strip()
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}")
    res = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    if iso.any():
        res.loc[iso] = pd.to_datetime(s[iso], format="mixed", errors="coerce", utc=True).dt.tz_localize(None).dt.round("D")
    if (~iso).any():
        res.loc[~iso] = pd.to_datetime(s[~iso], format="mixed", dayfirst=True, errors="coerce").dt.round("D")
    return res

# ==========================================
# ECRÃ DE LOGIN COM ESCOLHA DE SETOR
# ==========================================
if not st.session_state["usr_nome"]:
    setor_sel = st.radio(
        "Escolher Setor",
        ["🗼 Rede Móvel", "⚡ Eletricidade"],
        index=0 if "Rede" in st.session_state["setor"] else 1,
        horizontal=True
    )
    st.session_state["setor"] = setor_sel
    cfg_login = obter_config_setor(setor_sel)

    st.title(cfg_login["titulo"])
    st.subheader("🔐 Iniciar Sessão")

    with st.form("form_login"):
        u_in = st.text_input("Utilizador")
        s_in = st.text_input("Senha / PIN", type="password")
        entrar = st.form_submit_button(f"Entrar em {setor_sel}", type="primary", use_container_width=True)

    if entrar:
        chave_sec = cfg_login["secret_key"]
        if chave_sec not in st.secrets:
            st.error(f"Falta adicionar '{chave_sec}' nos Secrets do Streamlit para ligar à base de dados de {setor_sel}.")
            st.stop()

        url_login = st.secrets[chave_sec]
        u_clean = u_in.strip().lower()
        s_clean = s_in.strip()
        if u_clean == "admin" and s_clean == "1234":
            st.session_state["usr_nome"] = "admin"
            st.session_state["usr_perfil"] = "Admin"
            st.rerun()
        else:
            try:
                _, _, df_u_login, _, _, _ = ler_servidor(url_login)
                for col in ["Utilizador", "Senha", "Perfil"]:
                    df_u_login[col] = df_u_login[col].fillna("").astype(str).str.strip()
                df_u_login["Senha"] = df_u_login["Senha"].str.replace(r"\.0$", "", regex=True)
                match = df_u_login[(df_u_login["Utilizador"].str.lower() == u_clean) & (df_u_login["Senha"] == s_clean)]
                if not match.empty:
                    nome_u = match.iloc[0]["Utilizador"]
                    perf = match.iloc[0]["Perfil"].strip().lower()
                    st.session_state["usr_nome"] = nome_u
                    if u_clean == "admin" or perf in ["admin", "administrador", ""]:
                        st.session_state["usr_perfil"] = "Admin"
                    else:
                        st.session_state["usr_perfil"] = "Diário"
                    st.rerun()
                else:
                    st.error("Utilizador ou senha incorretos.")
            except Exception as e:
                st.error(f"Erro ao ligar à folha Google ({setor_sel}): {e}")
    st.stop()

# ==========================================
# CABEÇALHO E CARREGAMENTO DE DADOS DO SETOR ATIVO
# ==========================================
cfg = obter_config_setor(st.session_state["setor"])
chave_ativa = cfg["secret_key"]

if chave_ativa not in st.secrets:
    st.error(f"Falta configurar '{chave_ativa}' nos Secrets do Streamlit.")
    if st.button("⬅️ Voltar ao Login"):
        st.session_state["usr_nome"] = ""
        st.rerun()
    st.stop()

url_ativa = st.secrets[chave_ativa]

ct1, ct2 = st.columns([3, 1])
ct1.title(cfg["titulo"])
if ct2.button(f"🚪 Sair ({st.session_state['usr_nome']})", use_container_width=True):
    st.session_state["usr_nome"] = ""
    st.session_state["usr_perfil"] = ""
    st.rerun()

with st.spinner(f"A carregar dados ({st.session_state['setor']})..."):
    try:
        df_obras, df_elem, df_users, df_meios, df_mat, df_diario = ler_servidor(url_ativa)
    except Exception as erro:
        st.error(f"Erro ao ligar à folha Google ({st.session_state['setor']}): {erro}")
        if st.button("🔄 Tentar novamente"):
            st.cache_data.clear()
            st.rerun()
        st.stop()

for col in ["ID Obra", "Nome da Obra", "Cliente", "Estado", "PDF", "Fotos"]:
    df_obras[col] = df_obras[col].fillna("").astype(str).str.strip()
df_obras["ID Obra"] = df_obras["ID Obra"].str.replace(r"\.0$", "", regex=True)
df_obras["Estado"] = df_obras["Estado"].apply(normalizar_estado)
sem_id_obra = (df_obras["ID Obra"] == "") & (df_obras["Nome da Obra"] != "")
if sem_id_obra.any():
    df_obras.loc[sem_id_obra, "ID Obra"] = [f"OB-{i+1:02d}" for i in df_obras[sem_id_obra].index]
for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[col] = pd.to_numeric(df_obras[col], errors="coerce").fillna(0.0)
df_obras = df_obras[df_obras["ID Obra"] != ""].copy()

df_elem["Elemento"] = df_elem["Elemento"].fillna("").astype(str).str.strip()
df_elem["Valor_Dia"] = pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)
df_elem = df_elem[df_elem["Elemento"] != ""].copy()

for col in ["Utilizador", "Senha", "Perfil"]:
    df_users[col] = df_users[col].fillna("").astype(str).str.strip()
df_users["Senha"] = df_users["Senha"].str.replace(r"\.0$", "", regex=True)
df_users.loc[df_users["Perfil"] == "", "Perfil"] = "Admin"
df_users = df_users[df_users["Utilizador"] != ""].copy()
if df_users.empty:
    df_users = pd.DataFrame([{"Utilizador": "admin", "Senha": "1234", "Perfil": "Admin"}])

df_meios["Meio / Equipamento"] = df_meios["Meio / Equipamento"].fillna("").astype(str).str.strip()
df_meios["Valor_Dia"] = pd.to_numeric(df_meios["Valor_Dia"], errors="coerce").fillna(0.0)
df_meios = df_meios[df_meios["Meio / Equipamento"] != ""].copy()

for col in ["Material", "Unidade"]:
    df_mat[col] = df_mat[col].fillna("").astype(str).str.strip()
df_mat["Preco_Unitario"] = pd.to_numeric(df_mat["Preco_Unitario"], errors="coerce").fillna(0.0)
df_mat = df_mat[df_mat["Material"] != ""].copy()

for col in ["Data", "ID Obra", "Elemento", "Meio", "Material", "Notas"]:
    df_diario[col] = df_diario[col].fillna("").astype(str).str.strip()
df_diario["ID Obra"] = df_diario["ID Obra"].str.replace(r"\.0$", "", regex=True)
for col in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia", "Dias Falta"]:
    df_diario[col] = pd.to_numeric(df_diario[col], errors="coerce").fillna(0.0)

preco_colab = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
preco_meio = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
preco_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unid_mat = dict(zip(df_mat["Material"], df_mat["Unidade"]))
nomes_obras = dict(zip(df_obras["ID Obra"], df_obras["Nome da Obra"]))
estados_obras = dict(zip(df_obras["ID Obra"], df_obras["Estado"]))
pdfs_obras = dict(zip(df_obras["ID Obra"], df_obras["PDF"]))
fotos_obras = dict(zip(df_obras["ID Obra"], df_obras["Fotos"]))

if st.session_state["aviso"]:
    st.success(st.session_state["aviso"])
    st.session_state["aviso"] = ""

is_admin = (st.session_state["usr_perfil"] == "Admin") or (st.session_state["usr_nome"].strip().lower() == "admin")

if is_admin:
    aba = st.radio("Navegação", ["📝 Diário", "👷 Presenças", "💰 Contas", "⚙️ Tabelas"], horizontal=True, label_visibility="collapsed")
else:
    st.caption(f"👤 Sessão iniciada como **{st.session_state['usr_nome']}** ({st.session_state['setor']} — Registo Diário)")
    aba = "📝 Diário"
st.divider()

def etiqueta_obra(x):
    tag_pdf = " 📎PDF" if str(pdfs_obras.get(x, "")).startswith("http") else ""
    qtd_f = len(separar_links_fotos(fotos_obras.get(x, "")))
    tag_ft = f" 📷{qtd_f}" if qtd_f > 0 else ""
    return f"{x} — {nomes_obras.get(x, '')} [{estados_obras.get(x, '')}]{tag_pdf}{tag_ft}"

# ==========================================
# 1. DIÁRIO DE OBRA (SEM OBRAS CONCLUÍDAS + FALTAS)
# ==========================================
if aba == "📝 Diário":
    k = st.session_state["ciclo"]
    obras_disp = df_obras[~df_obras["Estado"].str.lower().isin(["concluída", "concluida"])].copy()
    clientes_ativos = sorted([c for c in obras_disp["Cliente"].unique().tolist() if c])

    if clientes_ativos:
        cli_f = st.selectbox("👤 Cliente", ["Todos"] + clientes_ativos, key="d_cli")
        if cli_f != "Todos":
            obras_disp = obras_disp[obras_disp["Cliente"] == cli_f]

    ids_disp = obras_disp["ID Obra"].tolist()
    obra_sel = st.selectbox("🏢 Obra", ids_disp, format_func=etiqueta_obra) if ids_disp else None

    if not obra_sel:
        st.info("Sem obras ativas disponíveis no Diário (as obras concluídas estão ocultas).")
    else:
        mostrar_anexos_obra(
            obra_sel,
            nomes_obras.get(obra_sel, ""),
            pdfs_obras.get(obra_sel, ""),
            fotos_obras.get(obra_sel, "")
        )
        st.divider()

    dt_reg = st.date_input("📅 Data", value=date.today())

    eq_sel = st.multiselect("👷 Colaboradores em Obra (regista presença)", list(preco_colab.keys()), placeholder="Escolher colaboradores...", key=f"eq_{k}")
    dias_eq = {}
    for n in eq_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{n}**")
        dias_eq[n] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"de_{n}_{k}")

    ft_sel = st.multiselect("🚫 Faltas de Colaboradores (regista ausência)", list(preco_colab.keys()), placeholder="Escolher colaboradores em falta...", key=f"ft_col_{k}")
    dias_ft = {}
    motivo_ft = {}
    for n in ft_sel:
        c1, c2, c3 = st.columns([2, 1, 2])
        c1.markdown(f"**{n}** *(Falta)*")
        dias_ft[n] = c2.number_input("Dias Falta", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"df_{n}_{k}")
        motivo_ft[n] = c3.text_input("Motivo", placeholder="Motivo (opcional)...", label_visibility="collapsed", key=f"mf_{n}_{k}")

    vi_sel = st.multiselect("🚚 Viaturas / Meios", list(preco_meio.keys()), placeholder="Escolher viaturas...", key=f"vi_{k}")
    dias_vi = {}
    for n in vi_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{n}**")
        dias_vi[n] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"dv_{n}_{k}")

    mt_sel = st.multiselect(
        "📦 Material Aplicado",
        list(preco_mat.keys()),
        format_func=lambda m: f"{m} ({unid_mat[m]})" if unid_mat.get(m) else m,
        placeholder="Escolher materiais...",
        key=f"mt_{k}"
    )
    qtd_mt = {}
    for n in mt_sel:
        c1, c2 = st.columns([2, 1])
        u = unid_mat.get(n, "")
        c1.markdown(f"**{n}** ({u})" if u else f"**{n}**")
        qtd_mt[n] = c2.number_input("Qtd", 0.0, value=1.0, step=1.0, label_visibility="collapsed", key=f"qm_{n}_{k}")

    obs = st.text_input("📝 Notas / Trabalhos realizados", key=f"ob_{k}")

    fotos_diario = st.file_uploader(
        "📷 Anexar Fotografias da Obra (podes tirar foto ou escolher várias)",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key=f"ft_d_{k}"
    )

    if st.button("💾 Gravar Registo Diário", type="primary", use_container_width=True):
        if not obra_sel:
            st.error("Seleciona uma obra ativa.")
        elif not eq_sel and not ft_sel and not vi_sel and not mt_sel and not obs.strip() and not fotos_diario:
            st.error("Preenche pelo menos um campo ou adiciona uma fotografia.")
        else:
            with st.spinner("A gravar registo e fotografias..."):
                try:
                    n_fotos = 0
                    if fotos_diario:
                        n_fotos = adicionar_fotos_obra(df_obras, obra_sel, fotos_diario, url_ativa)

                    l_eq = [(c, dias_eq[c]) for c in eq_sel if dias_eq[c] > 0]
                    l_ft = [(c, dias_ft[c], motivo_ft[c].strip()) for c in ft_sel if dias_ft[c] > 0]
                    l_vi = [(v, dias_vi[v]) for v in vi_sel if dias_vi[v] > 0]
                    l_mt = [(m, qtd_mt[m]) for m in mt_sel if qtd_mt[m] > 0]

                    max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
                    prox = int(0 if pd.isna(max_id) else max_id) + 1
                    dt_iso = dt_reg.strftime("%Y-%m-%d")
                    linhas_novas = []

                    tem_principal = bool(l_eq or l_vi or l_mt or obs.strip())
                    if tem_principal:
                        for i in range(max(len(l_eq), len(l_vi), len(l_mt), 1)):
                            en, ed = l_eq[i] if i < len(l_eq) else ("", 0.0)
                            vn, vd = l_vi[i] if i < len(l_vi) else ("", 0.0)
                            mn, mq = l_mt[i] if i < len(l_mt) else ("", 0.0)
                            ce, cv, cm = preco_colab.get(en, 0.0) * ed, preco_meio.get(vn, 0.0) * vd, preco_mat.get(mn, 0.0) * mq
                            linhas_novas.append({
                                "ID_Registo": prox, "Data": dt_iso, "ID Obra": obra_sel,
                                "Elemento": en, "Dias Elemento": ed, "Custo Elemento": ce,
                                "Meio": vn, "Dias Meio": vd, "Custo Meio": cv,
                                "Material": mn, "Qtd Material": mq, "Custo Material": cm,
                                "Total do Dia": ce + cv + cm, "Notas": obs if i == 0 else "",
                                "Dias Falta": 0.0
                            })
                            prox += 1

                    for fn, fd, fmot in l_ft:
                        nota_f = f"FALTA ({fmot})" if fmot else "FALTA"
                        linhas_novas.append({
                            "ID_Registo": prox, "Data": dt_iso, "ID Obra": obra_sel,
                            "Elemento": fn, "Dias Elemento": 0.0, "Custo Elemento": 0.0,
                            "Meio": "", "Dias Meio": 0.0, "Custo Meio": 0.0,
                            "Material": "", "Qtd Material": 0.0, "Custo Material": 0.0,
                            "Total do Dia": 0.0, "Notas": nota_f,
                            "Dias Falta": fd
                        })
                        prox += 1

                    if linhas_novas:
                        atualizado = pd.concat([df_diario, pd.DataFrame(linhas_novas)], ignore_index=True)
                        guardar_aba(url_ativa, "Registos_Diarios", atualizado)
                    else:
                        atualizado = df_diario

                    recalcular_obras(url_ativa, df_obras, atualizado)
                    st.cache_data.clear()
                    st.session_state["ciclo"] += 1
                    msg_ft = f", {len(l_ft)} falta(s)" if l_ft else ""
                    msg_foto = f" e {n_fotos} foto(s)" if n_fotos else ""
                    st.session_state["aviso"] = f"Gravado ({len(l_eq)} presença(s){msg_ft}{msg_foto})!"
                    st.rerun()
                except Exception as e:
                    st.error(f"Erro ao gravar: {e}")

    if obra_sel:
        st.divider()
        h_obra = df_diario[df_diario["ID Obra"] == obra_sel].copy()
        h_obra["Data_dt"] = converter_datas(h_obra["Data"])
        h_obra = h_obra.sort_values("Data_dt", ascending=False)
        h_obra["Data"] = h_obra["Data_dt"].dt.strftime("%d/%m/%Y").fillna(h_obra["Data"])
        cols_h = ["ID_Registo", "Data", "Elemento", "Dias Elemento", "Dias Falta", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]

        if is_admin:
            st.subheader("Histórico da Obra (Edição Admin)")
            ed_h = st.data_editor(h_obra[cols_h], num_rows="dynamic", use_container_width=True, hide_index=True, disabled=["ID_Registo"])
            if st.button("Atualizar Histórico / Apagar Linhas", use_container_width=True):
                ed = ed_h.copy()
                ed["Data"] = converter_datas(ed["Data"]).dt.strftime("%Y-%m-%d").fillna(ed["Data"].astype(str))
                ed["ID Obra"] = obra_sel
                for cn in ["Dias Elemento", "Dias Falta", "Dias Meio", "Qtd Material"]:
                    ed[cn] = pd.to_numeric(ed[cn], errors="coerce").fillna(0.0)
                ed["Custo Elemento"] = ed.apply(lambda r: preco_colab.get(str(r["Elemento"]), 0.0) * r["Dias Elemento"], axis=1)
                ed["Custo Meio"] = ed.apply(lambda r: preco_meio.get(str(r["Meio"]), 0.0) * r["Dias Meio"], axis=1)
                ed["Custo Material"] = ed.apply(lambda r: preco_mat.get(str(r["Material"]), 0.0) * r["Qtd Material"], axis=1)
                ed["Total do Dia"] = ed["Custo Elemento"] + ed["Custo Meio"] + ed["Custo Material"]
                final = pd.concat([df_diario[df_diario["ID Obra"] != obra_sel], ed[df_diario.columns.tolist()]], ignore_index=True)
                guardar_aba(url_ativa, "Registos_Diarios", final)
                recalcular_obras(url_ativa, df_obras, final)
                st.cache_data.clear()
                st.session_state["aviso"] = "Histórico atualizado!"
                st.rerun()
        else:
            st.subheader("📋 Histórico da Obra (Apenas Consulta)")
            if not h_obra.empty:
                cols_consulta = ["Data", "Elemento", "Dias Elemento", "Dias Falta", "Meio", "Dias Meio", "Material", "Qtd Material", "Notas"]
                st.dataframe(
                    h_obra[cols_consulta].rename(columns={
                        "Elemento": "Colaborador",
                        "Dias Elemento": "Dias Col.",
                        "Dias Falta": "Faltas",
                        "Meio": "Viatura",
                        "Dias Meio": "Dias Viat.",
                        "Qtd Material": "Qtd"
                    }),
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("Ainda não existem registos diários nesta obra.")

# ==========================================
# 2. PRESENÇAS E FALTAS (CALENDÁRIO + FINS DE SEMANA À PARTE)
# ==========================================
elif aba == "👷 Presenças":
    st.subheader("👷 Mapa de Presenças e Faltas")
    base_pt = df_diario[df_diario["Elemento"] != ""].copy()
    base_pt["Data_dt"] = converter_datas(base_pt["Data"])
    base_pt = base_pt[base_pt["Data_dt"].notna()].copy()

    hoje = date.today()
    anos_pt = sorted(set([hoje.year - 1, hoje.year, hoje.year + 1] + (base_pt["Data_dt"].dt.year.tolist() if not base_pt.empty else [])))
    lista_eq = sorted(set(list(preco_colab.keys()) + (base_pt["Elemento"].unique().tolist() if not base_pt.empty else [])))

    c1, c2, c3 = st.columns([2, 1, 2])
    mes_n = c1.selectbox("📅 Mês", list(MESES.keys()), index=hoje.month - 1, format_func=lambda m: MESES[m], key="pt_m")
    ano_n = c2.selectbox("Ano", anos_pt, index=anos_pt.index(hoje.year), key="pt_a")
    colab_f = c3.selectbox("👷 Colaborador", ["Todos"] + lista_eq, key="pt_c")

    flt = base_pt[(base_pt["Data_dt"].dt.year == ano_n) & (base_pt["Data_dt"].dt.month == mes_n)].copy()
    if colab_f != "Todos":
        flt = flt[flt["Elemento"] == colab_f]

    flt["FDS"] = flt["Data_dt"].dt.dayofweek >= 5
    flt["Uteis"] = flt["Dias Elemento"].where(~flt["FDS"], 0.0)
    flt["SabDom"] = flt["Dias Elemento"].where(flt["FDS"], 0.0)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Dias Úteis (Seg–Sex)", f"{float(flt['Uteis'].sum()):.1f} d")
    k2.metric("Fim de Semana (Sáb/Dom)", f"{float(flt['SabDom'].sum()):.1f} d")
    k3.metric("Total Trabalhado", f"{float(flt['Dias Elemento'].sum()):.1f} d")
    k4.metric("Faltas", f"{float(flt['Dias Falta'].sum()):.1f} d")

    if not flt.empty:
        quadro_res = flt.groupby("Elemento", as_index=False).agg(
            **{
                "Dias Úteis": ("Uteis", "sum"),
                "Sáb / Dom": ("SabDom", "sum"),
                "Total Dias": ("Dias Elemento", "sum"),
                "Faltas": ("Dias Falta", "sum"),
                "Obras": ("ID Obra", lambda s: ", ".join(sorted(set(s.astype(str)))))
            }
        ).rename(columns={"Elemento": "Colaborador"})
        st.dataframe(quadro_res, use_container_width=True, hide_index=True)

    mapa_dia = {}
    if not flt.empty:
        ag = flt.groupby([flt["Data_dt"].dt.day, "Elemento", "ID Obra"], as_index=False)[["Dias Elemento", "Dias Falta"]].sum()
        for _, r in ag.iterrows():
            dn = int(r["Data_dt"])
            alvo = r["Elemento"] if colab_f == "Todos" else r["ID Obra"]
            if r["Dias Elemento"] > 0:
                mapa_dia.setdefault(dn, []).append(f"{alvo} ({r['Dias Elemento']:.1f}d)")
            if r["Dias Falta"] > 0:
                mapa_dia.setdefault(dn, []).append(f"{alvo} (FALTA {r['Dias Falta']:.1f}d)")

    semanas_mes = calendar.monthcalendar(ano_n, mes_n)
    nomes_sem = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    grelha = []
    for sem in semanas_mes:
        linha = {}
        for idx, d in enumerate(sem):
            if d == 0:
                linha[nomes_sem[idx]] = ""
            else:
                itens = " • ".join(mapa_dia.get(d, []))
                linha[nomes_sem[idx]] = f"Dia {d:02d}: {itens}" if itens else f"Dia {d:02d}"
        grelha.append(linha)

    df_calendario = pd.DataFrame(grelha, index=[f"Sem. {i}" for i in range(1, len(semanas_mes) + 1)])

    def pintar_util(v):
        s = str(v)
        if not s:
            return "background-color: #f8fafc; color: #94a3b8;"
        if ":" in s:
            if "FALTA" in s and "d)" not in s.replace("FALTA ", ""):
                return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
            return "background-color: #dbeafe; color: #1e3a8a; font-weight: 700;"
        return "color: #475569;"

    def pintar_fds(v):
        s = str(v)
        if not s:
            return "background-color: #f8fafc; color: #94a3b8;"
        if ":" in s:
            if "FALTA" in s and "d)" not in s.replace("FALTA ", ""):
                return "background-color: #fee2e2; color: #991b1b; font-weight: 700;"
            return "background-color: #fde68a; color: #78350f; font-weight: 700;"
        return "background-color: #fffbeb; color: #b45309;"

    est_cal = df_calendario.style
    if hasattr(est_cal, "map"):
        est_cal = est_cal.map(pintar_util, subset=["Seg", "Ter", "Qua", "Qui", "Sex"]).map(pintar_fds, subset=["Sáb", "Dom"])
    else:
        est_cal = est_cal.applymap(pintar_util, subset=["Seg", "Ter", "Qua", "Qui", "Sex"]).applymap(pintar_fds, subset=["Sáb", "Dom"])

    st.markdown(f"**🗓️ Calendário Mensal — {MESES[mes_n]} / {ano_n}**")
    st.dataframe(est_cal, use_container_width=True)

    if not flt.empty:
        with st.expander("Ver lista detalhada por dia, faltas e notas"):
            det = flt.sort_values(["Data_dt", "Elemento"]).copy()
            det["Data"] = det["Data_dt"].dt.strftime("%d/%m/%Y")
            det["Tipo"] = det.apply(
                lambda r: "Falta" if r["Dias Falta"] > 0 and r["Dias Elemento"] == 0 else ("Fim de Semana" if r["FDS"] else "Dia Útil"),
                axis=1
            )
            st.dataframe(
                det[["Data", "Tipo", "Elemento", "ID Obra", "Dias Elemento", "Dias Falta", "Notas"]].rename(
                    columns={"Elemento": "Colaborador", "Dias Elemento": "Dias Trab.", "Dias Falta": "Faltas"}
                ),
                use_container_width=True,
                hide_index=True
            )

        pdf = FPDF(orientation="L", unit="mm", format="A4")
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        tit = f"{cfg['pdf_cab']} | MAPA DE PRESENCAS E FALTAS - {MESES[mes_n].upper()} / {ano_n}" + (f" ({colab_f})" if colab_f != "Todos" else "")
        pdf.cell(0, 8, txt_pdf(tit, 95), ln=True, align="C")
        pdf.ln(2)

        pdf.set_font("Helvetica", "B", 8)
        for cab, larg, al in [("Colaborador", 70, "L"), ("Dias Uteis", 26, "C"), ("Sab / Dom", 28, "C"), ("Total Trab.", 26, "C"), ("Faltas", 22, "C"), ("Obras", 105, "L")]:
            pdf.cell(larg, 6, cab, 1, align=al)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for _, r in quadro_res.iterrows():
            pdf.cell(70, 6, txt_pdf(r["Colaborador"], 35), 1)
            pdf.cell(26, 6, f"{r['Dias Úteis']:.1f}", 1, align="C")
            pdf.cell(28, 6, f"{r['Sáb / Dom']:.1f}", 1, align="C")
            pdf.cell(26, 6, f"{r['Total Dias']:.1f}", 1, align="C")
            pdf.cell(22, 6, f"{r['Faltas']:.1f}", 1, align="C")
            pdf.cell(105, 6, txt_pdf(r["Obras"], 52), 1)
            pdf.ln()

        pdf.ln(4)
        cab_sem = ["Segunda", "Terca", "Quarta", "Quinta", "Sexta", "Sabado (FDS)", "Domingo (FDS)"]
        larg_c = 39.5
        pdf.set_font("Helvetica", "B", 8)
        for i, ds in enumerate(cab_sem):
            pdf.set_fill_color(254, 243, 199) if i >= 5 else pdf.set_fill_color(241, 245, 249)
            pdf.cell(larg_c, 6, ds, 1, align="C", fill=True)
        pdf.ln()

        alt_disp = max(90.0, 195.0 - pdf.get_y())
        alt_lin = max(16.0, alt_disp / max(len(semanas_mes), 1))
        for sem in semanas_mes:
            x0, y0 = pdf.get_x(), pdf.get_y()
            for i, d in enumerate(sem):
                xc = x0 + i * larg_c
                pdf.set_xy(xc, y0)
                if d == 0:
                    pdf.set_fill_color(248, 250, 252)
                    pdf.cell(larg_c, alt_lin, "", 1, fill=True)
                else:
                    pdf.set_fill_color(255, 251, 235) if i >= 5 else pdf.set_fill_color(255, 255, 255)
                    pdf.rect(xc, y0, larg_c, alt_lin, style="DF")
                    pdf.set_xy(xc + 1.5, y0 + 1)
                    pdf.set_font("Helvetica", "B", 8)
                    pdf.cell(larg_c - 3, 4, str(d))
                    itens_d = mapa_dia.get(d, [])
                    if itens_d:
                        pdf.set_xy(xc + 1.5, y0 + 5)
                        pdf.set_font("Helvetica", "", 6.5)
                        bloco = "\n".join(itens_d[:4]) + (f"\n+{len(itens_d)-4}..." if len(itens_d) > 4 else "")
                        pdf.multi_cell(larg_c - 3, 3.1, txt_pdf(bloco, 140))
            pdf.set_xy(x0, y0 + alt_lin)

        st.download_button(
            "📥 Descarregar Calendário de Presenças e Faltas (PDF)",
            bytes_pdf(pdf),
            file_name=f"Presencas_{cfg['pdf_tag']}_{mes_n:02d}_{ano_n}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
    else:
        st.info(f"Sem presenças ou faltas registadas em {MESES[mes_n]} de {ano_n}.")

# ==========================================
# 3. CONTAS (POR CLIENTE, ESTADO E OBRA)
# ==========================================
elif aba == "💰 Contas":
    st.subheader("💰 Contas e Orçamentos")
    obras_ct = df_obras.copy()
    clientes_todos = sorted([c for c in df_obras["Cliente"].unique().tolist() if c])

    fc1, fc2 = st.columns(2)
    cli_c = fc1.selectbox("👤 Cliente", ["Todos"] + clientes_todos, key="c_cli") if clientes_todos else "Todos"
    est_c = fc2.multiselect("📌 Estado da Obra", ESTADOS_OBRA, default=ESTADOS_OBRA, key="c_est")

    if cli_c != "Todos":
        obras_ct = obras_ct[obras_ct["Cliente"] == cli_c]
    if est_c:
        obras_ct = obras_ct[obras_ct["Estado"].isin(est_c)]

    if cli_c != "Todos" or len(est_c) < len(ESTADOS_OBRA):
        adj_c = float(obras_ct["Valor Adjudicado"].sum())
        gas_c = float(obras_ct["Total Gasto"].sum())
        st.caption(f"Acumulado do filtro ({len(obras_ct)} obra(s))")
        c1, c2, c3 = st.columns(3)
        c1.metric("Adjudicado Filtro", f"{adj_c:,.2f} €")
        c2.metric("Gasto Filtro", f"{gas_c:,.2f} €")
        c3.metric("Saldo Filtro", f"{adj_c - gas_c:,.2f} €")
        st.divider()

    ids_ct = obras_ct["ID Obra"].tolist()
    if ids_ct:
        ob_c = st.selectbox("🏢 Obra", ids_ct, format_func=etiqueta_obra, key="c_ob")
        mostrar_anexos_obra(
            ob_c,
            nomes_obras.get(ob_c, ""),
            pdfs_obras.get(ob_c, ""),
            fotos_obras.get(ob_c, "")
        )

        info = df_obras[df_obras["ID Obra"] == ob_c].iloc[0]
        reg_ob = df_diario[df_diario["ID Obra"] == ob_c].copy()

        v_adj = float(info["Valor Adjudicado"])
        g_eq = float(reg_ob["Custo Elemento"].sum())
        g_vi = float(reg_ob["Custo Meio"].sum())
        g_mt = float(reg_ob["Custo Material"].sum())
        g_tot = g_eq + g_vi + g_mt
        v_sal = v_adj - g_tot

        m1, m2, m3 = st.columns(3)
        m1.metric("Valor Obra", f"{v_adj:,.2f} €")
        m2.metric("Total Gasto", f"{g_tot:,.2f} €")
        m3.metric("Saldo", f"{v_sal:,.2f} €")

        if v_adj > 0:
            st.progress(min(g_tot / v_adj, 1.0), text=f"Orçamento consumido: {(g_tot / v_adj) * 100:.1f}% | Estado: {info['Estado']}")
            if v_sal < 0:
                st.warning(f"⚠️ Orçamento ultrapassado em {abs(v_sal):,.2f} €")

        st.markdown("**Gastos por Categoria**")
        g1, g2, g3 = st.columns(3)
        g1.metric("👷 Colaboradores", f"{g_eq:,.2f} €")
        g2.metric("🚚 Viaturas", f"{g_vi:,.2f} €")
        g3.metric("📦 Materiais", f"{g_mt:,.2f} €")

        st.divider()
        st.markdown("**Todos os Gastos da Obra**")
        if not reg_ob.empty:
            reg_ob["Data_dt"] = converter_datas(reg_ob["Data"])
            reg_ob = reg_ob.sort_values("Data_dt", ascending=False)
            reg_ob["Data"] = reg_ob["Data_dt"].dt.strftime("%d/%m/%Y").fillna(reg_ob["Data"])
            cols_g = ["Data", "Elemento", "Dias Elemento", "Dias Falta", "Custo Elemento", "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas"]
            st.dataframe(
                reg_ob[cols_g].rename(columns={
                    "Elemento": "Colaborador", "Dias Elemento": "Dias Col.", "Dias Falta": "Faltas", "Custo Elemento": "€ Col.",
                    "Meio": "Viatura", "Dias Meio": "Dias Viat.", "Custo Meio": "€ Viat.",
                    "Qtd Material": "Qtd", "Custo Material": "€ Mat.", "Total do Dia": "Total (€)"
                }),
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Sem gastos registados nesta obra.")

        st.divider()
        st.subheader("📊 Quadro Geral de Obras")
        st.dataframe(
            obras_ct[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado", "PDF", "Fotos"]].rename(
                columns={"Valor Adjudicado": "Valor Obra (€)", "Total Gasto": "Gasto (€)", "Saldo Restante": "Saldo (€)"}
            ),
            use_container_width=True,
            hide_index=True,
            column_config={"PDF": st.column_config.LinkColumn("PDF", display_text="📄 Abrir")}
        )
    else:
        st.info("Sem obras para os filtros selecionados.")

# ==========================================
# 4. TABELAS DE BASE DE DADOS E UTILIZADORES
# ==========================================
elif aba == "⚙️ Tabelas":
    with st.expander("🖼️ Configurar Imagem de Fundo (Marca de Água)", expanded=False):
        fich_bg = st.file_uploader("Escolher imagem de fundo (LousaMaia)", type=["jpg", "jpeg", "png", "webp"], key="up_bg_app")
        if st.button("💾 Aplicar Imagem de Fundo", use_container_width=True):
            if not fich_bg:
                st.error("Escolhe a imagem primeiro.")
            else:
                with open("fundo.jpg", "wb") as f_bg:
                    f_bg.write(fich_bg.getvalue())
                st.session_state["aviso"] = "Imagem de fundo aplicada!"
                st.rerun()

    st.subheader("📎 Associar PDF ou Fotografias a uma Obra")
    ids_todas = df_obras["ID Obra"].tolist()
    if ids_todas:
        obra_up = st.selectbox("Selecionar ID Obra", ids_todas, format_func=etiqueta_obra, key="up_obra")
        col_pdf, col_ft = st.columns(2)

        with col_pdf:
            fich_pdf = st.file_uploader("📄 Escolher PDF da Obra", type=["pdf"], key="up_file_pdf")
            if st.button("📤 Carregar PDF", use_container_width=True):
                if not fich_pdf:
                    st.error("Escolhe um ficheiro PDF primeiro.")
                else:
                    with st.spinner("A enviar PDF para o Google Drive..."):
                        try:
                            nome_limpo = f"{obra_up}_{fich_pdf.name}"
                            url_drive = enviar_ficheiro_drive(url_ativa, nome_limpo, fich_pdf.getvalue(), mime_type="application/pdf")
                            df_obras.loc[df_obras["ID Obra"] == obra_up, "PDF"] = url_drive
                            recalcular_obras(url_ativa, df_obras, df_diario)
                            st.cache_data.clear()
                            st.session_state["aviso"] = f"PDF associado com sucesso à obra {obra_up}!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao carregar PDF: {e}")

        with col_ft:
            fichs_fotos = st.file_uploader(
                "📷 Escolher Fotografias (podes selecionar várias)",
                type=["jpg", "jpeg", "png", "webp"],
                accept_multiple_files=True,
                key="up_files_fotos"
            )
            if st.button("📷 Carregar Fotografias", use_container_width=True):
                if not fichs_fotos:
                    st.error("Escolhe pelo menos uma fotografia.")
                else:
                    with st.spinner("A enviar fotografias para o Google Drive..."):
                        try:
                            qtd_env = adicionar_fotos_obra(df_obras, obra_up, fichs_fotos, url_ativa)
                            recalcular_obras(url_ativa, df_obras, df_diario)
                            st.cache_data.clear()
                            st.session_state["aviso"] = f"{qtd_env} fotografia(s) associada(s) à obra {obra_up}!"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao carregar fotografias: {e}")

            fotos_atuais_ob = separar_links_fotos(fotos_obras.get(obra_up, ""))
            if fotos_atuais_ob:
                if st.button(f"🗑️ Limpar as {len(fotos_atuais_ob)} foto(s) desta obra", use_container_width=True):
                    df_obras.loc[df_obras["ID Obra"] == obra_up, "Fotos"] = ""
                    recalcular_obras(url_ativa, df_obras, df_diario)
                    st.cache_data.clear()
                    st.session_state["aviso"] = f"Fotografias removidas da obra {obra_up}!"
                    st.rerun()

    st.divider()

    st.subheader("🔐 Utilizadores e Acessos")
    st.caption("Perfil 'Admin' vê tudo | Perfil 'Diário' vê apenas o Registo Diário.")
    ed_u = st.data_editor(
        df_users,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Perfil": st.column_config.SelectboxColumn("Perfil", options=["Admin", "Diário"], default="Admin", required=True)
        }
    )

    st.subheader("🏢 Obras Atribuídas")
    st.caption("Estados disponíveis: Nova, Execução, Parcial, Concluída.")
    outros_est = [e for e in df_obras["Estado"].unique().tolist() if e and e not in ESTADOS_OBRA]
    ed_o = st.data_editor(
        df_obras[["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Estado", "PDF", "Fotos"]],
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Estado": st.column_config.SelectboxColumn(
                "Estado",
                options=ESTADOS_OBRA + outros_est,
                default="Nova",
                required=True
            ),
            "PDF": st.column_config.LinkColumn("PDF", display_text="📄 Abrir PDF")
        }
    )

    st.subheader("👷 Colaboradores (Valor/Dia)")
    ed_e = st.data_editor(df_elem, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("🚚 Viaturas / Meios (Valor/Dia)")
    ed_v = st.data_editor(df_meios, num_rows="dynamic", use_container_width=True, hide_index=True)
    st.subheader("📦 Materiais (Preço Unitário)")
    ed_m = st.data_editor(df_mat, num_rows="dynamic", use_container_width=True, hide_index=True)

    if st.button("💾 Guardar Todas as Tabelas", type="primary", use_container_width=True):
        ed_o["ID Obra"] = ed_o["ID Obra"].fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        ed_o["Valor Adjudicado"] = pd.to_numeric(ed_o["Valor Adjudicado"], errors="coerce").fillna(0.0)
        ed_o["Total Gasto"] = 0.0
        ed_o["Saldo Restante"] = ed_o["Valor Adjudicado"]
        recalcular_obras(url_ativa, ed_o, df_diario)
        guardar_elementos_e_users(url_ativa, ed_e, ed_u)
        guardar_aba(url_ativa, "Meios", ed_v)
        guardar_aba(url_ativa, "Materiais", ed_m)
        st.cache_data.clear()
        st.session_state["aviso"] = "Tabelas e utilizadores guardados!"
        st.rerun()
