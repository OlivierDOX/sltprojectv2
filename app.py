import streamlit as st
import pandas as pd
from itertools import combinations_with_replacement
from pulp import LpProblem, LpVariable, LpMinimize, lpSum, PULP_CBC_CMD

st.set_page_config(layout="wide")
st.markdown("<style> .block-container { max-width: 60%; } </style>", unsafe_allow_html=True)

st.title("Cálculo de Planos de Corte de Bobinas")

# Entradas do usuário
limite_inferior = st.text_input("Limite Inferior (%)", "90")
limite_superior = st.text_input("Limite Superior (%)", "130")

try:
    limite_inferior = float(limite_inferior) / 100
    limite_superior = float(limite_superior) / 100
except ValueError:
    st.error("Os limites inferior e superior devem ser números válidos em porcentagem.")
    st.stop()

# Largura da bobina fixa
larguras_bobina = [1192, 1191, 1190, 1189, 1188]
peso_bobina = 17715

# Definições dos produtos
produtos = {
    "Perfil UDC Enrijecido 50x25x10x2,00x6000mm": 105,
    "Perfil UDC Enrijecido 75x40x15x2,00x6000mm": 170,
    "Perfil UDC Enrijecido 100x40x15x2,00x6000mm": 197,
    "Perfil UDC Enrijecido 100x50x17x2,00x6000mm": 219,
    "Perfil UDC Enrijecido 127x50x17x2,00x6000mm": 244,
    "Perfil UDC Enrijecido 150x50x17x2,00x6000mm": 264,
    "Perfil UDC Enrijecido 150x60x20x2,00x6000mm": 295,
    "Perfil UDC Enrijecido 200x75x25x2,00x6000mm": 375,
    "Perfil UDC Simples 50x25x2,00x6000mm": 93,
    "Perfil UDC Simples 68x30x2,00x6000mm": 122,
    "Perfil UDC Simples 92x30x2,00x6000mm": 148,
    "Perfil UDC Simples 100x40x2,00x6000mm": 173,
    "Perfil UDC Simples 100x50x2,00x6000mm": 192,
    "Perfil UDC Simples 127x50x2,00x6000mm": 217,
    "Perfil UDC Simples 150x50x2,00x6000mm": 242,
    "Perfil UDC Simples 200x75x2,00x6000mm": 343
}

larguras_slitters = list(produtos.values())

# Entrada de demandas como seleção múltipla
with st.expander("Selecione os produtos"):
    df_produtos = pd.DataFrame({"Produto": list(produtos.keys()), "Selecionado": [False] * len(produtos)})
    df_editado = st.data_editor(df_produtos, num_rows="fixed", use_container_width=True, hide_index=True)
    produtos_selecionados = df_editado[df_editado["Selecionado"] == True]["Produto"].tolist()

demands = []
for produto in produtos_selecionados:
    peso = st.number_input(f"Peso para {produto} (kg)", min_value=1, step=1)
    largura = produtos[produto]
    demands.append({"width": largura, "weight": peso})

def encontra_combinacoes_possiveis(larguras_slitters, largura_bobina):
    combinacoes = []
    for n in range(1, largura_bobina // min(larguras_slitters) + 1):
        for combinacao in combinations_with_replacement(larguras_slitters, n):
            if sum(combinacao) == largura_bobina:
                combinacoes.append(combinacao)
    return combinacoes

def resolver_problema_corte(larguras_slitters, largura_bobina, peso_bobina, demandas):
    proporcao = peso_bobina / largura_bobina

    combinacoes = encontra_combinacoes_possiveis(larguras_slitters, largura_bobina)

    if not combinacoes:
        return None

    problema = LpProblem("Problema_de_Corte", LpMinimize)
    x = LpVariable.dicts("Plano", range(len(combinacoes)), lowBound=0, cat="Integer")

    problema += lpSum(x[i] for i in range(len(combinacoes))), "Minimizar_Bobinas"

    for demanda in demandas:
        largura = demanda["width"]
        peso_necessario = demanda["weight"]

        problema += (
            lpSum(
                x[i] * combinacao.count(largura) * proporcao * largura
                for i, combinacao in enumerate(combinacoes)
            ) >= peso_necessario * limite_inferior,
            f"Atender_Minima_{largura}",
        )
        problema += (
            lpSum(
                x[i] * combinacao.count(largura) * proporcao * largura
                for i, combinacao in enumerate(combinacoes)
            ) <= peso_necessario * limite_superior,
            f"Atender_Maxima_{largura}",
        )

    problema.solve(PULP_CBC_CMD(msg=False))

    if problema.status != 1:
        return None

    resultado = []
    for i, combinacao in enumerate(combinacoes):
        if x[i].varValue > 0:
            pesos_por_largura = [largura * proporcao for largura in combinacao]
            combinacao_com_pesos = [
                f"{largura} | {round(peso, 0)} kg"
                for largura, peso in zip(combinacao, pesos_por_largura)
            ]

            puxada = 2 if any(peso > 5000 for peso in pesos_por_largura) else 1

            resultado.append(
                {
                    "Plano de Corte": combinacao_com_pesos,
                    "Quantidade": int(x[i].varValue),
                    "Largura Total": sum(combinacao),
                    "Puxada": puxada,
                }
            )

    return pd.DataFrame(resultado)

def gerar_tabela_final(resultado, demandas, proporcao, produtos):
    pesos_totais = {demanda["width"]: 0 for demanda in demandas}
    for _, linha in resultado.iterrows():
        combinacao = linha["Plano de Corte"]
        quantidade = linha["Quantidade"]
        for item in combinacao:
            largura = int(str(item).split('|')[0].strip())
            pesos_totais[largura] += quantidade * largura * proporcao
    tabela_final = []
    for demanda in demandas:
        largura = demanda["width"]
        peso_planejado = demanda["weight"]
        peso_total = pesos_totais.get(largura, 0)
        percentual_atendido = (peso_total / peso_planejado * 100) if peso_planejado > 0 else 0
        produto = next((key for key, value in produtos.items() if value == largura), "Produto Desconhecido")
        tabela_final.append({
            "Largura (mm)": largura,
            "Produto": produto,
            "Demanda Planejada (kg)": peso_planejado,
            "Peso Total (kg)": round(peso_total, 0),
            "Atendimento (%)": round(percentual_atendido, 1),
        })
    totais = {
        "Largura (mm)": "Total",
        "Produto": "",
        "Demanda Planejada (kg)": sum(d["weight"] for d in demandas),
        "Peso Total (kg)": round(sum(pesos_totais.values()), 0),
        "Atendimento (%)": round(sum(pesos_totais.values()) / sum(d["weight"] for d in demandas) * 100, 1) if sum(d["weight"] for d in demandas) > 0 else 0,
    }
    tabela_final.append(totais)
    df_final = pd.DataFrame(tabela_final)
    df_final = df_final.applymap(lambda x: f"{int(x):,}".replace(",", ".") if isinstance(x, (int, float)) and x == round(x, 0) else (f"{x:,}".replace(",", ".") if isinstance(x, (int, float)) else x))
    return df_final


def exibir_dataframe(df):
    st.dataframe(df, use_container_width=True, height=(len(df) * 35 + 50), hide_index=True)


# Botão para calcular
if st.button("Calcular"):
    melhor_resultado = None
    melhor_largura = None
    for largura_bobina in larguras_bobina:
        resultado = resolver_problema_corte(larguras_slitters, largura_bobina, peso_bobina, demands)
        if resultado is not None:
            if melhor_resultado is None or resultado["Quantidade"].sum() < melhor_resultado["Quantidade"].sum():
                melhor_resultado = resultado
                melhor_largura = largura_bobina
    if melhor_resultado is not None:
        proporcao = peso_bobina / melhor_largura
        tabela_final = gerar_tabela_final(melhor_resultado, demands, proporcao, produtos)
        st.subheader("Melhor largura de bobina")
        st.write(f"{melhor_largura} mm")
        st.subheader("Resultado dos Planos de Corte")
        st.dataframe(melhor_resultado)
        st.subheader("Tabela Final")
        st.dataframe(tabela_final)
        resultado_txt = tabela_final.to_string(index=False) + "\n\n" + melhor_resultado.to_string(index=False)
        st.download_button(
            label="Baixar Resultado (TXT)",
            data=resultado_txt.encode("utf-8"),
            file_name="resultado_corte.txt",
            mime="text/plain"
        )
    else:
        st.error("Nenhuma solução encontrada!")
