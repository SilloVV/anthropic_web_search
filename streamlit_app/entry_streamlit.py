import streamlit as st

st.set_page_config(
    page_title="Hello",
    page_icon="👋",
)

st.write("# Bienvenue dans le Streamlit IA! 👋")

st.sidebar.success("↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑")

st.markdown(
    """
    <--- Choisis la page que tu veux explorer
"""
)


st.markdown("""
<style>
.image-70-percent {
    margin-left: 70%;
    transform: translateX(-50%);
}
</style>
""", unsafe_allow_html=True)

