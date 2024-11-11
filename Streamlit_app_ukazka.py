import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
from snowflake.snowpark import Session
 
st.markdown("""
## 🎯 Cíl Ukázky
 
Hlavním cílem je ukázat, jak **Streamlit** a **Snowflake** společně umožňují rychlý vývoj interaktivních aplikací s jednoduchým propojením na AI.
 
## ⚙️ Jak to funguje?
 
S využitím **Streamlit** pro snadnou tvorbu webových aplikací a propojením na **Snowflake** můžeme:
- **Analyzovat data** s pomocí AI modelů v reálném čase
- **Vizualizovat** trendy a struktury v datech interaktivně
- **Upravovat** případy a komentáře přímo v aplikaci
- **Přidávat nové záznamy** díky jednoduchým formulářům
 
Tato kombinace poskytuje nástroje pro rychlý vývoj i produkční nasazení bez hlubokých znalostí webového vývoje.
""")
 
# Použití stávající session ve Snowflake Streamlit
session = Session.builder.getOrCreate()
 
# Načítání dat přímo ze Snowflake s použitím Snowpark session
def load_cases_data():
    query = """
    SELECT CASE_ID, CUSTOMER_ID, CASE_TYPE, STATUS, PRIORITY, DATE_OPENED, NOTE
    FROM bank_cases
    """
    return session.sql(query).to_pandas()
 
# Načtení dat
cases_df = load_cases_data()
 
# Funkce pro získání maximálního ID z databáze
def get_max_case_id():
    query = "SELECT MAX(CASE_ID) AS max_id FROM bank_cases"
    result = session.sql(query).collect()
    return result[0]['MAX_ID'] + 1 if result[0]['MAX_ID'] is not None else 1
 
# EDA - Porovnání struktury případů za posledních 14 dní vs. celkové období
st.title("Ukázka:")
st.markdown("---")
 
def calculate_case_structure(df, period="Celkové období"):
    case_structure = df.groupby(['CASE_TYPE', 'PRIORITY']).size().reset_index(name=f'{period} (%)')
    case_structure[f'{period} (%)'] = (case_structure[f'{period} (%)'] / case_structure[f'{period} (%)'].sum()) * 100
    return case_structure
 
# Filtrování na posledních 14 dní
recent_cases_df = cases_df[cases_df['DATE_OPENED'] >= (datetime.now() - timedelta(days=14)).date()]
 
# Spojení celkového období a posledních 14 dnů
total_structure = calculate_case_structure(cases_df, "Celkové období")
recent_structure = calculate_case_structure(recent_cases_df, "Posledních 14 dní")
merged_structure = total_structure.merge(recent_structure, on=["CASE_TYPE", "PRIORITY"], how="outer").fillna(0)
 
# Výpočet rozdílu
merged_structure['DIFF_PERCENT'] = merged_structure['Posledních 14 dní (%)'] - merged_structure['Celkové období (%)']
 
 
# Vizualizace sloupcového grafu pro porovnání struktury podle typu případu a priority
st.subheader("Porovnání struktury případů - Celkové období vs. Posledních 14 dní")
fig_compare = go.Figure()
colors = ['#a2d5f2', '#ffa07a']
for idx, priority in enumerate(merged_structure['PRIORITY'].unique()):
    priority_data = merged_structure[merged_structure['PRIORITY'] == priority]
    fig_compare.add_trace(go.Bar(
        x=priority_data['CASE_TYPE'],
        y=priority_data['Celkové období (%)'],
        name=f'Celkové období ({priority})',
        marker_color=colors[0]
    ))
    fig_compare.add_trace(go.Bar(
        x=priority_data['CASE_TYPE'],
        y=priority_data['Posledních 14 dní (%)'],
        name=f'Posledních 14 dní ({priority})',
        marker_color=colors[1],
    ))
 
fig_compare.update_layout(
    barmode='group',
    xaxis_title="Typ případu",
    yaxis_title="Procento",
    title="Porovnání struktury případů podle typu a priority",
    showlegend=True
)
st.plotly_chart(fig_compare)
 
# Shrnutí rozdílů jako text pro Cortex
summary_text = "Analyzujte rozdíly v procentech mezi celkovým obdobím a posledními 14 dny:\n"
for _, row in merged_structure.iterrows():
    summary_text += f"Typ případu: {row['CASE_TYPE']}, Priorita: {row['PRIORITY']}, Rozdíl: {row['DIFF_PERCENT']:.2f}%\n"
 
# Předání textu do Cortexu bez parametrizace
def analyze_with_cortex(summary):
    query = f"SELECT snowflake.cortex.COMPLETE('llama3.2-3b','{summary}') AS INTERPRETATION"
    result = session.sql(query).collect()
    return result[0][0] if result else "Žádné výsledky."
 
# Tlačítko pro generování interpretace
if st.button("Zobrazit interpretaci rozdílů"):
    comments = analyze_with_cortex(summary_text)
    #st.subheader("Komentáře k rozdílům:")
    with st.expander("Komentáře k rozdílům", expanded=True):
        st.write(comments)
 
st.markdown("---")
 
# Interaktivní tabulka nejrizikovějších případů
st.subheader("Nejrizikovější případy za posledních 14 dní")
recent_high_risk = recent_cases_df[recent_cases_df['PRIORITY'] == 'Vysoká'].head(10)
 
# Umožnění úprav sloupců STATUS a Poznámka
editable_df = recent_high_risk[['CASE_ID', 'CUSTOMER_ID', 'CASE_TYPE', 'PRIORITY', 'STATUS', 'NOTE']].copy()
editable_df = editable_df.rename(columns={'NOTE': 'Poznámka'})
editable_df['CUSTOMER_ID'] = editable_df['CUSTOMER_ID'].apply(lambda x: '{:,.0f}'.format(x).replace(',', ' '))
 
# Interaktivní úprava s výběrem možnosti pro sloupec STATUS
status_options = ["Otevřeno", "Řešeno", "Uzavřeno"]
editable_df['STATUS'] = editable_df['STATUS'].astype("category")
 
# Zobrazení upravitelné tabulky s novou funkcí `st.data_editor`
edited_df = st.data_editor(editable_df, use_container_width=True, hide_index=True)
 
# Uložení změn do databáze
if st.button("Uložit změny stavů a poznámky"):
    for _, row in edited_df.iterrows():
        case_id = row['CASE_ID']
        new_status = row['STATUS']
        note = row['Poznámka']
        update_query = f"""
        UPDATE bank_cases
        SET STATUS = '{new_status}', NOTE = '{note}'
        WHERE CASE_ID = {case_id}
        """
        session.sql(update_query).collect()
    st.success("Změny stavů a poznámky byly uloženy do databáze.")
 
# Formulář pro přidání nového případu
st.sidebar.header("Přidat nový případ")
 
# Možnost zadat nové ID, nebo použít automatické navýšení
max_case_id = get_max_case_id()
new_case_id = st.sidebar.number_input("ID nového případu", min_value=max_case_id, value=max_case_id)
 
new_case_type = st.sidebar.selectbox("Typ případu", ["Reklamace transakce", "Žádost o úvěr", "Změna limitu", "Zablokování karty"])
new_customer_id = st.sidebar.number_input("ID zákazníka", min_value=1000, max_value=1050)
new_priority = st.sidebar.selectbox("Priorita", ["Vysoká", "Střední", "Nízká"])
 
if st.sidebar.button("Přidat nový případ"):
    insert_query = f"""
    INSERT INTO bank_cases (CASE_ID, CUSTOMER_ID, CASE_TYPE, STATUS, PRIORITY, DATE_OPENED, NOTE)
    VALUES ({new_case_id}, {new_customer_id}, '{new_case_type}', 'Otevřeno', '{new_priority}', CURRENT_DATE(), NULL)
    """
    session.sql(insert_query).collect()
    st.sidebar.success("Nový případ byl přidán")
 
st.markdown("---")
 
# Sunburst graf pro strukturu případů s jemnějšími barvami
st.subheader("Struktura případů dle priority a typu (Sunburst)")
 
fig_sunburst = px.sunburst(
    cases_df,
    path=['PRIORITY', 'CASE_TYPE'],
    values='CUSTOMER_ID',
    color='PRIORITY',
    color_discrete_map={'Vysoká': '#ff7f7f', 'Střední': '#ffd700', 'Nízká': '#90ee90'},
)
fig_sunburst.update_layout(margin=dict(t=0, l=0, r=0, b=0))
st.plotly_chart(fig_sunburst, use_container_width=True)
