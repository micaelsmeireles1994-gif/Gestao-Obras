import streamlit as st
import pandas as pd
import calendar
from datetime import date
import requests
import json
from fpdf import FPDF

st.set_page_config(page_title="Gestão de Obras", page_icon="🏗️", layout="centered")
st.session_state.setdefault("ciclo", 0)
st.session_state.setdefault("aviso", "")
st.session_state.setdefault("usr_nome", "")
st.session_state.setdefault("usr_perfil", "")

MESES = {
    1: "01 - Janeiro", 2: "02 - Fevereiro", 3: "03 - Março", 4: "04 - Abril",
    5: "05 - Maio", 6: "06 - Junho", 7: "07 - Julho", 8: "08 - Agosto",
    9: "09 - Setembro", 10: "10 - Outubro", 11: "11 - Novembro", 12: "12 - Dezembro"
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
def ler_servidor():
    r = requests.get(st.secrets["apps_script_url"], timeout=15)
    r.raise_for_status()
    pacote = r.json()

    def extrair(aba, cols, sin=None):
        df = pd.DataFrame(pacote.get(aba, []))
        if df.empty:
            return pd.DataFrame(columns=cols)
        if sin:
            df = ajustar_colunas(df, sin)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]

    obras = extrair(
        "Obras",
        ["ID Obra", "Nome da Obra", "Cliente", "Valor Adjudicado", "Total Gasto", "Saldo Restante", "Estado"],
        {"ID Obra": ["ID", "Codigo", "Código"], "Nome da Obra": ["Obra", "Nome"], "Valor Adjudicado": ["Valor", "Orcamento", "Orçamento"]}
    )
    elem_raw = extrair(
        "Elementos",
        ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"],
        {"Elemento": ["Colaborador", "Colaboradores", "Nome"], "Valor_Dia": ["Valor Dia", "Valor/Dia", "Custo_Dia", "Valor"]}
    )
    elem = elem_raw[["Elemento", "Valor_Dia"]].copy()
    users = elem_raw[["Utilizador", "Senha", "Perfil"]].copy()
    meios = extrair(
        "Meios",
        ["Meio / Equipamento", "Valor_Dia"],
        {"Meio / Equipamento": ["Viatura", "Viaturas", "Meio", "Equipamento"], "Valor_Dia": ["Valor Dia", "Valor/Dia", "Valor"]}
    )
    mat = extrair(
        "Materiais",
        ["Material", "Unidade", "Preco_Unitario"],
        {"Material": ["Nome", "Artigo"], "Unidade": ["Un", "Un."], "Preco_Unitario": ["Preco", "Preço", "Valor"]}
    )
    diario = extrair(
        "Registos_Diarios",
        ["ID_Registo", "Data", "ID Obra", "Elemento", "Dias Elemento", "Custo Elemento",
         "Meio", "Dias Meio", "Custo Meio", "Material", "Qtd Material", "Custo Material", "Total do Dia", "Notas"],
        {"Elemento": ["Colaborador"], "Meio": ["Viatura"]}
    )
    return obras, elem, users, meios, mat, diario

def guardar_aba(aba, df):
    limpo = df.fillna("")
    linhas = [limpo.columns.tolist()] + limpo.values.tolist()
    r = requests.post(
        st.secrets["apps_script_url"],
        data=json.dumps({"sheet": aba, "rows": linhas}),
        headers={"Content-Type": "text/plain;charset=utf-8"},
        timeout=20
    )
    r.raise_for_status()

def guardar_elementos_e_users(df_e, df_u):
    e_limpo = df_e[df_e["Elemento"].fillna("").astype(str).str.strip() != ""][["Elemento", "Valor_Dia"]].reset_index(drop=True)
    u_limpo = df_u[df_u["Utilizador"].fillna("").astype(str).str.strip() != ""][["Utilizador", "Senha", "Perfil"]].reset_index(drop=True)
    combinado = pd.concat([e_limpo, u_limpo], axis=1).fillna("")
    for col in ["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]:
        if col not in combinado.columns:
            combinado[col] = ""
    guardar_aba("Elementos", combinado[["Elemento", "Valor_Dia", "Utilizador", "Senha", "Perfil"]])

def recalcular_obras(df_o, df_d):
    o = df_o.copy()
    o["ID Obra"] = o["ID Obra"].fillna("").astype(str).str.strip()
    o["Valor Adjudicado"] = pd.to_numeric(o["Valor Adjudicado"], errors="coerce").fillna(0.0)
    gastos = {}
    if not df_d.empty:
        d = df_d.copy()
        d["ID Obra"] = d["ID Obra"].fillna("").astype(str).str.strip()
        d["Total do Dia"] = pd.to_numeric(d["Total do Dia"], errors="coerce").fillna(0.0)
        gastos = d.groupby("ID Obra")["Total do Dia"].sum().to_dict()
    o["Total Gasto"] = o["ID Obra"].map(gastos).fillna(0.0)
    o["Saldo Restante"] = o["Valor Adjudicado"] - o["Total Gasto"]
    guardar_aba("Obras", o)

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
# ECRÃ DE LOGIN IMEDIATO (NUNCA FICA EM BRANCO)
# ==========================================
if not st.session_state["usr_nome"]:
    st.title("🏗️ Gestão de Obras")
    st.subheader("🔐 Iniciar Sessão")
    with st.form("form_login"):
        u_in = st.text_input("Utilizador")
        s_in = st.text_input("Senha / PIN", type="password")
        entrar = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if entrar:
        u_clean = u_in.strip().lower()
        s_clean = s_in.strip()
        if u_clean == "admin" and s_clean == "1234":
            st.session_state["usr_nome"] = "admin"
            st.session_state["usr_perfil"] = "Admin"
            st.rerun()
        else:
            try:
                _, _, df_u_login, _, _, _ = ler_servidor()
                for col in ["Utilizador", "Senha", "Perfil"]:
                    df_u_login[col] = df_u_login[col].fillna("").astype(str).str.strip()
                df_u_login["Senha"] = df_u_login["Senha"].str.replace(r"\.0$", "", regex=True)
                match = df_u_login[(df_u_login["Utilizador"].str.lower() == u_clean) & (df_u_login["Senha"] == s_clean)]
                if not match.empty:
                    st.session_state["usr_nome"] = match.iloc[0]["Utilizador"]
                    perf = match.iloc[0]["Perfil"].strip().lower()
                    st.session_state["usr_perfil"] = "Admin" if perf == "admin" else "Diário"
                    st.rerun()
                else:
                    st.error("Utilizador ou senha incorretos.")
            except Exception as e:
                st.error(f"Erro ao ligar à folha Google: {e}")
    st.stop()

# ==========================================
# CABEÇALHO E CARREGAMENTO DE DADOS
# ==========================================
ct1, ct2 = st.columns([3, 1])
ct1.title("🏗️ Gestão de Obras")
if ct2.button(f"🚪 Sair ({st.session_state['usr_nome']})", use_container_width=True):
    st.session_state["usr_nome"] = ""
    st.session_state["usr_perfil"] = ""
    st.rerun()

with st.spinner("A carregar dados da obra..."):
    try:
        df_obras, df_elem, df_users, df_meios, df_mat, df_diario = ler_servidor()
    except Exception as erro:
        st.error(f"Erro ao ligar à folha Google: {erro}")
        if st.button("🔄 Tentar novamente"):
            st.cache_data.clear()
            st.rerun()
        st.stop()

for col in ["ID Obra", "Nome da Obra", "Cliente", "Estado"]:
    df_obras[col] = df_obras[col].fillna("").astype(str).str.strip()
for col in ["Valor Adjudicado", "Total Gasto", "Saldo Restante"]:
    df_obras[col] = pd.to_numeric(df_obras[col], errors="coerce").fillna(0.0)
df_obras = df_obras[df_obras["ID Obra"] != ""].copy()

df_elem["Elemento"] = df_elem["Elemento"].fillna("").astype(str).str.strip()
df_elem["Valor_Dia"] = pd.to_numeric(df_elem["Valor_Dia"], errors="coerce").fillna(0.0)
df_elem = df_elem[df_elem["Elemento"] != ""].copy()

for col in ["Utilizador", "Senha", "Perfil"]:
    df_users[col] = df_users[col].fillna("").astype(str).str.strip()
df_users["Senha"] = df_users["Senha"].str.replace(r"\.0$", "", regex=True)
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
for col in ["Dias Elemento", "Custo Elemento", "Dias Meio", "Custo Meio", "Qtd Material", "Custo Material", "Total do Dia"]:
    df_diario[col] = pd.to_numeric(df_diario[col], errors="coerce").fillna(0.0)

preco_colab = dict(zip(df_elem["Elemento"], df_elem["Valor_Dia"]))
preco_meio = dict(zip(df_meios["Meio / Equipamento"], df_meios["Valor_Dia"]))
preco_mat = dict(zip(df_mat["Material"], df_mat["Preco_Unitario"]))
unid_mat = dict(zip(df_mat["Material"], df_mat["Unidade"]))
nomes_obras = dict(zip(df_obras["ID Obra"], df_obras["Nome da Obra"]))
clientes = sorted([c for c in df_obras["Cliente"].unique().tolist() if c])

if st.session_state["aviso"]:
    st.success(st.session_state["aviso"])
    st.session_state["aviso"] = ""

is_admin = (st.session_state["usr_perfil"] == "Admin")

if is_admin:
    aba = st.radio("Navegação", ["📝 Diário", "👷 Presenças", "💰 Contas", "⚙️ Tabelas", "📄 PDF"], horizontal=True, label_visibility="collapsed")
else:
    aba = "📝 Diário"
st.divider()

# ==========================================
# 1. DIÁRIO DE OBRA (SEM VALORES FINANCEIROS)
# ==========================================
if aba == "📝 Diário":
    k = st.session_state["ciclo"]
    obras_disp = df_obras[df_obras["Estado"].str.lower() != "concluída"]
    if obras_disp.empty:
        obras_disp = df_obras

    if clientes:
        cli_f = st.selectbox("👤 Cliente", ["Todos"] + clientes, key="d_cli")
        if cli_f != "Todos":
            obras_disp = obras_disp[obras_disp["Cliente"] == cli_f]

    ids_disp = obras_disp["ID Obra"].tolist()
    obra_sel = st.selectbox("🏢 Obra", ids_disp, format_func=lambda x: f"{x} — {nomes_obras.get(x, '')}") if ids_disp else None
    if not obra_sel:
        st.warning("Sem obras disponíveis.")

    dt_reg = st.date_input("📅 Data", value=date.today())

    eq_sel = st.multiselect("👷 Colaboradores em Obra (regista presença)", list(preco_colab.keys()), placeholder="Escolher colaboradores...", key=f"eq_{k}")
    dias_eq = {}
    for n in eq_sel:
        c1, c2 = st.columns([2, 1])
        c1.markdown(f"**{n}**")
        dias_eq[n] = c2.number_input("Dias", 0.0, value=1.0, step=0.5, label_visibility="collapsed", key=f"de_{n}_{k}")

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

    if st.button("💾 Gravar Registo Diário", type="primary", use_container_width=True):
        if not obra_sel:
            st.error("Seleciona uma obra.")
        elif not eq_sel and not vi_sel and not mt_sel and not obs.strip():
            st.error("Preenche pelo menos um campo.")
        else:
            max_id = pd.to_numeric(df_diario["ID_Registo"], errors="coerce").max()
            prox = int(0 if pd.isna(max_id) else max_id) + 1
            dt_iso = dt_reg.strftime("%Y-%m-%d")
            l_eq = [(c, dias_eq[c]) for c in eq_sel if dias_eq[c] > 0]
            l_vi = [(v, dias_vi[v]) for v in vi_sel if dias_vi[v] > 0]
            l_mt = [(m, qtd_mt[m]) for m in mt_sel if qtd_mt[m] > 0]
            linhas_novas = []
            for i in range(max(len(l_eq), len(l_vi), len(l_mt), 1)):
                en, ed = l_eq[i] if i < len(l_eq) else ("", 0.0)
                vn, vd = l_vi[i] if i < len(l_vi) else ("", 0.0)
                mn, mq = l_mt[i] if i < len(l_mt) else ("", 0.0)
                ce, cv, cm = preco_colab.get(en, 0.0) * ed, preco_meio.get(vn, 0.0) * vd, preco_mat.get(mn, 0.0) * mq
                linhas_novas.append({
                    "ID_Registo": prox + i, "Data": dt_iso, "ID Obra": obra_sel,
                    "Elemento": en, "Dias Elemento": ed, "Custo Elemento": ce,
                    "Meio": vn, "Dias Meio": vd, "Custo Meio": cv,
                    "Material": mn, "Qtd Material": mq, "Custo Material": cm,
                    "Total do Dia": ce + cv + cm, "Notas": obs if i == 0 else ""
                })
            atualizado = pd.concat([df_diario, pd.DataFrame(linhas_novas)], ignore_index=True)
            guardar_aba("Registos_Diarios", atualizado)
            recalcular_obras(df_obras, atualizado)
            st.cache_data.clear()
            st.session_state["ciclo"] += 1
            st.session_state["aviso"] = f"Gravado ({len(l_eq)} presença(s) registada(s))!"
            st.rerun()

    if obra_sel and is_admin:
        st.divider()
        st.subheader("Histórico da Obra")
        h_obra = df_diario[df_diario["ID Obra"] == obra_sel].copy()
        h_
