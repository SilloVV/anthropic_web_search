import streamlit as st

st.set_page_config(
    page_title="Hello",
    page_icon="👋",
)

st.write("# Bienvenue dans le Streamlit IA! 👋")

st.sidebar.success("Ceci est une barre latérale verte.")

st.markdown(
    """
    Choisis la page que tu veux explorer ci-dessus.
"""
)